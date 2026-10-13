use crate::model::{self, Entry, Settings};
use eframe::egui::{self, Color32, Pos2, Rect, RichText, Stroke, TextureHandle, Vec2};
use image::DynamicImage;
use serde_json::json;
use std::{
    collections::{HashMap, HashSet},
    fs,
    path::{Path, PathBuf},
    sync::{
        Arc,
        atomic::{AtomicBool, AtomicU64, Ordering},
        mpsc::{self, Receiver, Sender},
    },
    time::Duration,
};
const BLUE: Color32 = Color32::from_rgb(37, 99, 235);
const MUTED: Color32 = Color32::from_rgb(100, 116, 139);
const BORDER: Color32 = Color32::from_rgb(175, 192, 210);
const ORANGE: Color32 = Color32::from_rgb(249, 115, 22);

#[derive(Clone)]
struct RenderSpec {
    generation: u64,
    image: Arc<DynamicImage>,
    width: u32,
    height: u32,
    canvas: u32,
    step: u32,
    pages: u32,
}
struct RenderTask {
    spec: RenderSpec,
    page: u32,
}
enum Event {
    Loaded(u64, PathBuf, Result<DynamicImage, String>),
    Page(u64, u32, Result<egui::ColorImage, String>),
    Directory(PathBuf, Vec<Entry>),
    SearchResult(u64, PathBuf),
    SearchDone(u64, usize, bool, usize),
}
pub struct Viewer {
    settings: Settings,
    favorites: Vec<PathBuf>,
    selected: Option<PathBuf>,
    directory: Option<PathBuf>,
    file: Option<PathBuf>,
    tree: HashMap<PathBuf, Vec<Entry>>,
    tree_pending: HashSet<PathBuf>,
    expanded: HashSet<PathBuf>,
    roots: Vec<(PathBuf, String)>,
    tree_width: f32,
    center_selection: bool,
    image: Option<Arc<DynamicImage>>,
    scale: f64,
    overlap: f64,
    mask: bool,
    loading: bool,
    tx: Sender<Event>,
    rx: Receiver<Event>,
    render_tx: Sender<RenderTask>,
    generation: Arc<AtomicU64>,
    load_generation: u64,
    spec: Option<RenderSpec>,
    pages: HashMap<u32, TextureHandle>,
    requested: HashSet<u32>,
    failed: HashSet<u32>,
    scroll: f32,
    total_width: f32,
    canvas_height: u32,
    query: String,
    recursive: bool,
    search_id: u64,
    search_cancel: Arc<AtomicBool>,
    searching: bool,
    search_open: bool,
    results: Vec<PathBuf>,
    result_selected: Option<usize>,
    search_status: String,
    search_root: PathBuf,
    search_keyword: String,
    favorites_open: bool,
    draft: Vec<PathBuf>,
    draft_selected: Option<usize>,
    confirmation: Option<bool>,
    help_open: bool,
    help_reset_scroll: bool,
    message: Option<String>,
    dirty: bool,
    geometry_timer: std::time::Instant,
    maximize_on_start: bool,
}
impl Viewer {
    pub fn new(cc: &eframe::CreationContext<'_>) -> Self {
        let ctx = &cc.egui_ctx;
        ctx.set_theme(egui::Theme::Light);
        let mut fonts = egui::FontDefinitions::default();
        for path in [
            "C:/Windows/Fonts/msyh.ttc",
            "C:/Windows/Fonts/msyh.ttf",
            "C:/Windows/Fonts/simhei.ttf",
        ] {
            if let Ok(data) = fs::read(path) {
                fonts
                    .font_data
                    .insert("Chinese".into(), egui::FontData::from_owned(data).into());
                fonts
                    .families
                    .entry(egui::FontFamily::Proportional)
                    .or_default()
                    .insert(0, "Chinese".into());
                break;
            }
        }
        for (name, path) in [
            ("Emoji", "C:/Windows/Fonts/seguiemj.ttf"),
            ("Symbols", "C:/Windows/Fonts/seguisym.ttf"),
        ] {
            if let Ok(data) = fs::read(path) {
                fonts
                    .font_data
                    .insert(name.into(), egui::FontData::from_owned(data).into());
                fonts
                    .families
                    .entry(egui::FontFamily::Proportional)
                    .or_default()
                    .push(name.into());
            }
        }
        let fallback = fonts
            .families
            .get(&egui::FontFamily::Proportional)
            .cloned()
            .unwrap_or_default();
        for (family, path) in [
            ("HelpRegular", "C:/Windows/Fonts/msyh.ttc"),
            ("HelpBold", "C:/Windows/Fonts/msyhbd.ttc"),
        ] {
            let mut names = fallback.clone();
            if let Ok(bytes) = fs::read(path) {
                let mut font = egui::FontData::from_owned(bytes);
                font.index = 1; // Microsoft YaHei UI, matching the original Tk help page.
                fonts.font_data.insert(family.into(), font.into());
                names.insert(0, family.into());
            }
            fonts
                .families
                .insert(egui::FontFamily::Name(family.into()), names);
        }
        ctx.set_fonts(fonts);
        ctx.options_mut(|options| options.zoom_with_keyboard = false);
        let mut style = egui::Style::default();
        style.visuals = egui::Visuals::light();
        style.visuals.panel_fill = Color32::WHITE;
        style.visuals.window_fill = Color32::from_rgb(244, 247, 251);
        style.visuals.override_text_color = Some(Color32::from_rgb(30, 41, 59));
        style.visuals.selection.bg_fill = Color32::from_rgb(230, 240, 255);
        style.visuals.selection.stroke = Stroke::new(1.0_f32, BLUE);
        style.visuals.widgets.inactive.bg_fill = Color32::from_rgb(238, 243, 248);
        style.visuals.widgets.hovered.bg_fill = Color32::from_rgb(219, 234, 254);
        style.visuals.extreme_bg_color = Color32::from_rgb(248, 250, 252);
        style.visuals.widgets.inactive.corner_radius = egui::CornerRadius::same(12);
        style.visuals.widgets.hovered.corner_radius = egui::CornerRadius::same(12);
        style.visuals.widgets.active.corner_radius = egui::CornerRadius::same(12);
        style.visuals.widgets.open.corner_radius = egui::CornerRadius::same(12);
        style.spacing.interact_size.y = 30.0;
        style.spacing.scroll = egui::style::ScrollStyle::solid();
        style.spacing.scroll.bar_width = 14.0;
        style.spacing.scroll.bar_inner_margin = 3.0;
        style.spacing.scroll.dormant_background_opacity = 0.2;
        style.spacing.scroll.dormant_handle_opacity = 0.6;
        style.spacing.button_padding = Vec2::new(12.0, 6.0);
        style.spacing.item_spacing = Vec2::new(6.0, 5.0);
        style
            .text_styles
            .insert(egui::TextStyle::Body, egui::FontId::proportional(14.0));
        style
            .text_styles
            .insert(egui::TextStyle::Button, egui::FontId::proportional(14.0));
        ctx.set_style(style);
        let settings = Settings::load();
        let favorites = settings.favorites();
        let tree_width = settings
            .get("TreeWidth")
            .parse::<f32>()
            .unwrap_or(200.0)
            .max(100.0);
        let mask = settings.get("MaskEnabled") == "1";
        let last = PathBuf::from(settings.get("LastFile"));
        let (tx, rx) = mpsc::channel();
        let (render_tx, render_rx) = mpsc::channel::<RenderTask>();
        let generation = Arc::new(AtomicU64::new(0));
        let render_generation = generation.clone();
        let event_tx = tx.clone();
        let repaint = ctx.clone();
        std::thread::spawn(move || {
            while let Ok(task) = render_rx.recv() {
                if task.spec.generation != render_generation.load(Ordering::Relaxed) {
                    continue;
                }
                let s = &task.spec;
                let result = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
                    let resized = model::render_page(
                        &s.image,
                        s.width,
                        s.height,
                        s.canvas,
                        s.step,
                        task.page,
                        s.height > s.canvas,
                    );
                    egui::ColorImage::from_rgba_unmultiplied(
                        [resized.width() as usize, resized.height() as usize],
                        resized.as_raw(),
                    )
                }))
                .map_err(|_| "页面生成失败".to_owned());
                if s.generation == render_generation.load(Ordering::Relaxed) {
                    let _ = event_tx.send(Event::Page(s.generation, task.page, result));
                    repaint.request_repaint();
                }
            }
        });
        let mut app = Self {
            settings,
            favorites,
            selected: None,
            directory: None,
            file: None,
            tree: HashMap::new(),
            tree_pending: HashSet::new(),
            expanded: HashSet::new(),
            roots: drive_roots(),
            tree_width,
            center_selection: false,
            image: None,
            scale: 1.0,
            overlap: 0.2,
            mask,
            loading: false,
            tx,
            rx,
            render_tx,
            generation,
            load_generation: 0,
            spec: None,
            pages: HashMap::new(),
            requested: HashSet::new(),
            failed: HashSet::new(),
            scroll: 0.0,
            total_width: 1.0,
            canvas_height: 0,
            query: String::new(),
            recursive: false,
            search_id: 0,
            search_cancel: Arc::new(AtomicBool::new(false)),
            searching: false,
            search_open: false,
            results: Vec::new(),
            result_selected: None,
            search_status: "尚未开始搜索".into(),
            search_root: PathBuf::new(),
            search_keyword: String::new(),
            favorites_open: false,
            draft: Vec::new(),
            draft_selected: None,
            confirmation: None,
            help_open: false,
            help_reset_scroll: true,
            message: None,
            dirty: false,
            geometry_timer: std::time::Instant::now(),
            maximize_on_start: true,
        };
        if last.exists() {
            app.open_path(last, ctx);
        }
        if let Some(path) = std::env::args_os().nth(1) {
            let path = PathBuf::from(path);
            if path.exists() {
                app.open_path(path, ctx);
            }
        }
        app
    }
    fn persist(&mut self) {
        self.settings.set("TreeWidth", self.tree_width.round());
        self.settings
            .set("MaskEnabled", if self.mask { 1 } else { 0 });
        self.settings
            .set("Favorites", serde_json::to_string(&self.favorites).unwrap());
        if let Some(path) = self.file.as_ref().or(self.directory.as_ref()) {
            self.settings.set("LastFile", path.display());
        }
        if let Err(e) = self.settings.save() {
            self.message = Some(e);
        }
        self.dirty = false;
    }
    fn save_image(&mut self) {
        if let Some(file) = &self.file {
            if let Err(e) = model::save_image_settings(file, self.scale, self.overlap) {
                self.message = Some(e);
            }
        }
    }
    fn invalidate(&mut self) {
        self.generation.fetch_add(1, Ordering::Relaxed);
        self.spec = None;
        self.pages.clear();
        self.requested.clear();
        self.failed.clear();
    }
    fn open_path(&mut self, path: PathBuf, ctx: &egui::Context) {
        if !path.exists() {
            self.message = Some(format!("项目不存在：\n{}", path.display()));
            return;
        }
        let path = if path.is_absolute() {
            path
        } else {
            std::env::current_dir().unwrap().join(path)
        };
        if path.is_file() && !model::is_image(&path) {
            return;
        }
        self.selected = Some(path.clone());
        self.center_selection = true;
        let dir = if path.is_dir() {
            path.clone()
        } else {
            path.parent().unwrap().to_owned()
        };
        self.directory = Some(dir.clone());
        for ancestor in dir.ancestors() {
            self.expanded.insert(ancestor.to_owned());
            self.load_directory(ancestor.to_owned(), ctx);
        }
        self.dirty = true;
        if path.is_dir() {
            return;
        }
        self.save_image();
        (self.scale, self.overlap) = model::image_settings(&path);
        self.file = Some(path.clone());
        self.image = None;
        self.loading = true;
        self.scroll = 0.0;
        self.invalidate();
        self.load_generation += 1;
        let id = self.load_generation;
        let tx = self.tx.clone();
        let repaint = ctx.clone();
        std::thread::spawn(move || {
            let result = model::load_image(&path);
            let _ = tx.send(Event::Loaded(id, path, result));
            repaint.request_repaint();
        });
    }
    fn load_directory(&mut self, path: PathBuf, ctx: &egui::Context) {
        if self.tree.contains_key(&path) || !self.tree_pending.insert(path.clone()) {
            return;
        }
        let tx = self.tx.clone();
        let ctx = ctx.clone();
        std::thread::spawn(move || {
            let entries = model::entries(&path);
            let _ = tx.send(Event::Directory(path, entries));
            ctx.request_repaint();
        });
    }
    fn toggle_favorite(&mut self, path: PathBuf) {
        if let Some(i) = self.favorites.iter().position(|p| *p == path) {
            self.favorites.remove(i);
        } else if self.favorites.len() < 50 {
            self.favorites.push(path);
        } else {
            self.message = Some("收藏数量已达到50个限制，请先删除一些收藏".into());
        }
        self.persist();
    }
    fn sort(&mut self, method: &str, ctx: &egui::Context) {
        if let Some(dir) = self.directory.clone() {
            let config = dir.join("image_config.json");
            let mut v = model::read_json(&config);
            v["sort_method"] = json!(method);
            if let Err(e) = model::write_json(&config, &v) {
                self.message = Some(e);
            }
            self.tree.remove(&dir);
            self.load_directory(dir, ctx);
        }
    }
    fn events(&mut self, ctx: &egui::Context) {
        while let Ok(event) = self.rx.try_recv() {
            match event {
                Event::Loaded(id, path, result)
                    if id == self.load_generation && self.file.as_ref() == Some(&path) =>
                {
                    self.loading = false;
                    match result {
                        Ok(image) => self.image = Some(Arc::new(image)),
                        Err(e) => {
                            self.message = Some(format!("无法打开图片：\n{}\n{e}", path.display()))
                        }
                    };
                }
                Event::Page(id, page, result) if id == self.generation.load(Ordering::Relaxed) => {
                    self.requested.remove(&page);
                    match result {
                        Ok(image) => {
                            self.pages.insert(
                                page,
                                ctx.load_texture(
                                    format!("page-{id}-{page}"),
                                    image,
                                    egui::TextureOptions::LINEAR,
                                ),
                            );
                        }
                        Err(e) => {
                            self.failed.insert(page);
                            self.message = Some(e);
                        }
                    }
                }
                Event::Directory(path, entries) => {
                    self.tree_pending.remove(&path);
                    self.tree.insert(path, entries);
                }
                Event::SearchResult(id, path) if id == self.search_id => {
                    self.results.push(path);
                    self.search_status = format!("正在搜索……已找到 {} 个文件", self.results.len());
                }
                Event::SearchDone(id, count, stopped, errors) if id == self.search_id => {
                    self.searching = false;
                    self.search_status = format!(
                        "{}，找到 {count} 个文件{}",
                        if stopped {
                            "搜索已停止"
                        } else {
                            "搜索完成"
                        },
                        if errors > 0 {
                            format!("，跳过 {errors} 个无法访问的项目")
                        } else {
                            String::new()
                        }
                    );
                }
                _ => {}
            }
        }
    }
    fn start_search(&mut self, ctx: &egui::Context) {
        let Some(root) = self.directory.clone() else {
            self.message = Some("请先在目录树中打开一个文件夹。".into());
            return;
        };
        self.search_cancel.store(true, Ordering::Relaxed);
        self.search_cancel = Arc::new(AtomicBool::new(false));
        self.search_id += 1;
        self.searching = true;
        self.search_open = true;
        self.results.clear();
        self.result_selected = None;
        self.search_root = root.clone();
        self.search_keyword = self.query.trim().to_owned();
        self.search_status = "正在搜索……已找到 0 个文件".into();
        let id = self.search_id;
        let cancel = self.search_cancel.clone();
        let tx = self.tx.clone();
        let repaint = ctx.clone();
        let query = self.query.clone();
        let recursive = self.recursive;
        std::thread::spawn(move || {
            let mut emitted = 0;
            let (count, errors) = model::search_images(&root, &query, recursive, &cancel, |path| {
                emitted += 1;
                let _ = tx.send(Event::SearchResult(id, path));
                if emitted % 32 == 0 {
                    repaint.request_repaint();
                }
            });
            let _ = tx.send(Event::SearchDone(
                id,
                count,
                cancel.load(Ordering::Relaxed),
                errors,
            ));
            repaint.request_repaint();
        });
    }
    fn toolbar(&mut self, ctx: &egui::Context) {
        egui::TopBottomPanel::top("toolbar")
            .frame(
                egui::Frame::new()
                    .fill(Color32::WHITE)
                    .inner_margin(egui::Margin::symmetric(8, 6)),
            )
            .show(ctx, |ui| {
                if self.favorites_open || self.help_open {
                    ui.disable();
                }
                ui.horizontal(|ui| {
                    ui.menu_button("收藏夹  ▾", |ui| {
                        if ui.button("整理收藏夹…").clicked() {
                            self.draft = self.favorites.clone();
                            self.draft_selected = None;
                            self.favorites_open = true;
                            ui.close();
                        }
                        ui.separator();
                        if self.favorites.is_empty() {
                            ui.label("(空)");
                        }
                        for path in self.favorites.clone() {
                            let name = path
                                .file_name()
                                .unwrap_or(path.as_os_str())
                                .to_string_lossy();
                            if ui
                                .button(format!(
                                    "{} {name}",
                                    if path.is_dir() { "📁" } else { "📄" }
                                ))
                                .clicked()
                            {
                                if path.exists() {
                                    self.open_path(path, ctx);
                                } else {
                                    self.message =
                                        Some(format!("项目不存在：\n{}", path.display()));
                                    self.favorites.retain(|p| p != &path);
                                    self.persist();
                                }
                                ui.close();
                            }
                        }
                    });
                    ui.menu_button("排序  ▾", |ui| {
                        for (name, method) in [
                            ("时间倒序", "time_desc"),
                            ("时间顺序", "time_asc"),
                            ("名称倒序", "name_desc"),
                            ("名称顺序", "name_asc"),
                        ] {
                            if ui.button(name).clicked() {
                                self.sort(method, ctx);
                                ui.close();
                            }
                        }
                    });
                    if ui.checkbox(&mut self.mask, "遮罩").changed() {
                        self.dirty = true;
                    }
                    if ui.button("帮助").clicked() {
                        self.help_open = true;
                        self.help_reset_scroll = true;
                    }
                    ui.separator();
                    ui.label(RichText::new("搜索").color(MUTED));
                    let search =
                        ui.add(egui::TextEdit::singleline(&mut self.query).desired_width(256.0));
                    let enter = (search.has_focus() || search.lost_focus())
                        && ui.input(|i| i.key_pressed(egui::Key::Enter));
                    if ui
                        .add_enabled(
                            !self.searching,
                            egui::Button::new(RichText::new("搜索").color(Color32::WHITE))
                                .fill(BLUE),
                        )
                        .clicked()
                        || enter
                    {
                        self.start_search(ctx);
                    }
                    if ui
                        .add_enabled(self.searching, egui::Button::new("停止"))
                        .clicked()
                    {
                        self.search_cancel.store(true, Ordering::Relaxed);
                    }
                    ui.checkbox(&mut self.recursive, "搜索子文件夹");
                });
            });
    }
    fn tree_node(
        &mut self,
        ui: &mut egui::Ui,
        path: &Path,
        label: &str,
        depth: usize,
        ctx: &egui::Context,
    ) {
        if depth > 64 {
            return;
        }
        let path = path.to_owned();
        let open = self.expanded.contains(&path);
        let mut text = RichText::new(label);
        if self.favorites.contains(&path) {
            text = text.family(egui::FontFamily::Name("HelpBold".into())).color(BLUE);
        }
        ui.horizontal(|ui| {
            ui.add_space(depth as f32 * 16.0);
            if ui
                .add(
                    egui::Button::new(if open { "▾" } else { "▸" })
                        .frame(false)
                        .min_size(Vec2::new(14.0, 24.0)),
                )
                .clicked()
            {
                if open {
                    self.expanded.remove(&path);
                } else {
                    self.expanded.insert(path.clone());
                    self.load_directory(path.clone(), ctx);
                }
            }
            let response = list_row(
                ui,
                text,
                label,
                self.selected.as_ref() == Some(&path),
                25.0,
                false,
            );
            if response.clicked() {
                self.selected = Some(path.clone());
                self.directory = Some(path.clone());
                self.dirty = true;
                if open {
                    self.expanded.remove(&path);
                } else {
                    self.expanded.insert(path.clone());
                    self.load_directory(path.clone(), ctx);
                }
            }
            if response.secondary_clicked() {
                self.toggle_favorite(path.clone());
            }
            if self.center_selection && self.selected.as_ref() == Some(&path) {
                response.scroll_to_me(Some(egui::Align::Center));
                self.center_selection = false;
            }
        });
        if self.expanded.contains(&path) {
            if let Some(entries) = self.tree.get(&path).cloned() {
                for entry in entries {
                    let name = entry
                        .path
                        .file_name()
                        .unwrap_or_default()
                        .to_string_lossy()
                        .to_string();
                    if entry.directory {
                        self.tree_node(ui, &entry.path, &name, depth + 1, ctx);
                    } else {
                        let date: chrono::DateTime<chrono::Local> = entry.modified.into();
                        let mut text =
                            RichText::new(format!("{name} ({})", date.format("%Y-%m-%d")));
                        if self.favorites.contains(&entry.path) {
                            text = text.family(egui::FontFamily::Name("HelpBold".into())).color(BLUE);
                        }
                        ui.horizontal(|ui| {
                            ui.add_space((depth + 1) as f32 * 16.0 + 20.0);
                            let response = list_row(
                                ui,
                                text,
                                &name,
                                self.selected.as_ref() == Some(&entry.path),
                                25.0,
                                false,
                            );
                            if response.clicked() {
                                self.open_path(entry.path.clone(), ctx);
                            }
                            if response.secondary_clicked() {
                                self.toggle_favorite(entry.path.clone());
                            }
                            if self.center_selection && self.selected.as_ref() == Some(&entry.path)
                            {
                                response.scroll_to_me(Some(egui::Align::Center));
                                self.center_selection = false;
                            }
                        });
                    }
                }
            } else {
                self.load_directory(path, ctx);
                ui.label(RichText::new("正在读取目录……").color(MUTED));
            }
        }
    }
    fn canvas(&mut self, ui: &mut egui::Ui, ctx: &egui::Context) {
        gradient(ui, ui.max_rect());
        let available = ui.available_size();
        let height = (available.y - 18.0).max(20.0) as u32;
        if height != self.canvas_height {
            self.canvas_height = height;
            self.invalidate();
        }
        // Process geometry changes before cloning the render context. Otherwise the old
        // context can re-reserve pages after invalidate(), leaving new pages unrequested.
        if ui.is_enabled() && ui.rect_contains_pointer(ui.max_rect()) {
            if ui.input(|i| i.pointer.button_clicked(egui::PointerButton::Middle)) {
                self.mask = !self.mask;
                self.dirty = true;
            }
            let delta = ui.input(|i| i.raw_scroll_delta.y);
            if delta != 0.0 {
                if ui.input(|i| i.modifiers.ctrl) {
                    let overlap =
                        (self.overlap + if delta > 0.0 { 0.05 } else { -0.05 }).clamp(0.05, 0.3);
                    if (overlap - self.overlap).abs() > 1e-9 {
                        self.overlap = overlap;
                        self.save_image();
                        self.invalidate();
                        ctx.request_repaint();
                    }
                } else {
                    self.scroll = (self.scroll
                        - if delta > 0.0 {
                            self.total_width * 0.1
                        } else {
                            -self.total_width * 0.1
                        })
                    .clamp(0.0, (self.total_width - available.x).max(0.0));
                    ctx.request_repaint();
                }
            }
        }
        let old_width = self.total_width;
        if self.spec.is_none() {
            if let Some(image) = &self.image {
                let (width, step, pages, stride) = model::page_geometry(
                    image.width(),
                    image.height(),
                    self.scale,
                    height,
                    self.overlap,
                );
                self.total_width = (stride as f32 * pages as f32).max(1.0);
                self.scroll = if old_width > 0.0 {
                    self.scroll / old_width * self.total_width
                } else {
                    0.0
                };
                self.spec = Some(RenderSpec {
                    generation: self.generation.load(Ordering::Relaxed),
                    image: image.clone(),
                    width,
                    height: ((image.height() as f64 * self.scale) as u32).max(1),
                    canvas: height,
                    step,
                    pages,
                });
            }
        }
        let spec = self.spec.clone();
        let total = self.total_width;
        let scroll = egui::ScrollArea::horizontal()
            .id_salt("image_scroll")
            .auto_shrink([false, false])
            .scroll_bar_visibility(egui::scroll_area::ScrollBarVisibility::AlwaysVisible)
            .scroll_source(egui::scroll_area::ScrollSource::SCROLL_BAR)
            .horizontal_scroll_offset(self.scroll)
            .show_viewport(ui, |ui, viewport| {
                let (rect, _response) = ui.allocate_exact_size(
                    Vec2::new(total.max(available.x), height as f32),
                    egui::Sense::click(),
                );
                gradient(ui, rect);
                if let Some(s) = spec {
                    let split = s.height > s.canvas;
                    let stride = if split { s.width + 20 } else { s.width };
                    let first = ((viewport.min.x / stride as f32).floor() as u32).min(s.pages - 1);
                    let last = ((viewport.max.x / stride as f32).ceil() as u32).min(s.pages - 1);
                    let start = first.saturating_sub(2);
                    let end = (last + 2).min(s.pages - 1);
                    self.pages.retain(|p, _| *p >= start && *p <= end);
                    // Visible pages precede prefetch work in the queue.
                    let order = (first..=last)
                        .chain((start..first).rev())
                        .chain(last + 1..=end);
                    for page in order {
                        if !self.pages.contains_key(&page)
                            && !self.failed.contains(&page)
                            && model::reserve_page(
                                &mut self.requested,
                                s.generation,
                                self.generation.load(Ordering::Relaxed),
                                page,
                            )
                        {
                            if self
                                .render_tx
                                .send(RenderTask {
                                    spec: s.clone(),
                                    page,
                                })
                                .is_err()
                            {
                                self.requested.remove(&page);
                                self.failed.insert(page);
                                self.message = Some("页面渲染线程已停止，请重新打开程序。".into());
                            }
                        }
                    }
                    for page in first..=last {
                        let x = rect.left()
                            + page as f32 * stride as f32
                            + if split { 10.0 } else { 0.0 };
                        let y = rect.top() + if split { 10.0 } else { 0.0 };
                        let ph = if split {
                            s.canvas.min(s.height - page * s.step)
                        } else {
                            s.height
                        };
                        let image_rect = Rect::from_min_size(
                            Pos2::new(x, y),
                            Vec2::new(s.width as f32, ph as f32),
                        );
                        if split {
                            ui.painter().rect_stroke(
                                Rect::from_min_max(
                                    Pos2::new(x - 5.0, rect.top() + 5.0),
                                    Pos2::new(x + s.width as f32 + 5.0, rect.bottom() - 5.0),
                                ),
                                10.0,
                                Stroke::new(1.0_f32, BORDER),
                                egui::StrokeKind::Inside,
                            );
                        }
                        if let Some(texture) = self.pages.get(&page) {
                            ui.painter().image(
                                texture.id(),
                                image_rect,
                                Rect::from_min_max(Pos2::ZERO, Pos2::new(1.0, 1.0)),
                                Color32::WHITE,
                            );
                        } else {
                            ui.painter().text(
                                image_rect.center(),
                                egui::Align2::CENTER_CENTER,
                                if self.failed.contains(&page) {
                                    "页面生成失败".into()
                                } else {
                                    format!("正在生成第 {} 页……", page + 1)
                                },
                                egui::FontId::proportional(14.0),
                                MUTED,
                            );
                        }
                        if split {
                            let overlap = (s.canvas as f64 * self.overlap) as u32;
                            for oy in [
                                if page > 0 { Some(overlap as f32) } else { None },
                                if page < s.pages - 1 {
                                    Some((s.canvas - overlap) as f32)
                                } else {
                                    None
                                },
                            ]
                            .into_iter()
                            .flatten()
                            {
                                let line_y = y + oy;
                                if self.mask {
                                    let top = if oy == overlap as f32 { y } else { line_y };
                                    ui.painter().rect_filled(
                                        Rect::from_min_size(
                                            Pos2::new(x, top),
                                            Vec2::new(s.width as f32, overlap as f32),
                                        ),
                                        0.0,
                                        Color32::from_rgba_unmultiplied(15, 159, 145, 32),
                                    );
                                }
                                ui.painter().line_segment(
                                    [Pos2::new(x, line_y), Pos2::new(x + s.width as f32, line_y)],
                                    Stroke::new(2.0_f32, ORANGE),
                                );
                            }
                            ui.painter().text(
                                Pos2::new(x + s.width as f32 / 2.0, rect.bottom() - 20.0),
                                egui::Align2::CENTER_CENTER,
                                format!(
                                    "第 {}/{} 页 (重叠: {}%)",
                                    page + 1,
                                    s.pages,
                                    (self.overlap * 100.0).round()
                                ),
                                egui::FontId::proportional(13.0),
                                BLUE,
                            );
                        }
                    }
                } else if self.loading {
                    ui.painter().text(
                        rect.center(),
                        egui::Align2::CENTER_CENTER,
                        "正在读取图片……",
                        egui::FontId::proportional(16.0),
                        MUTED,
                    );
                }
            });
        // Preserve custom wheel scrolling; egui handles scrollbar drag separately.
        let wheel = ctx.input(|i| i.raw_scroll_delta.y != 0.0);
        if !wheel {
            self.scroll = scroll.state.offset.x;
        }
    }
    fn remember_geometry(&mut self, ctx: &egui::Context, _prefix: &str) {
        ctx.input(|i| {
            if i.viewport().maximized.unwrap_or(false) || i.viewport().minimized.unwrap_or(false) {
                return;
            }
            if let Some(rect) = i.viewport().outer_rect {
                self.dirty |= self.settings.set(
                    "SearchResultsPosition",
                    format!(
                        "{},{}",
                        rect.min.x.round() as i32,
                        rect.min.y.round() as i32
                    ),
                );
            }
            if let Some(rect) = i.viewport().inner_rect {
                self.dirty |= self.settings.set(
                    "SearchResultsSize",
                    format!(
                        "{}x{}",
                        rect.width().round() as i32,
                        rect.height().round() as i32
                    ),
                );
            }
        });
    }
    fn viewport_builder(&self, title: &str, prefix: &str, size: Vec2) -> egui::ViewportBuilder {
        let (desktop, primary) = desktop_bounds();
        let mut size = size;
        let search = prefix == "SearchResults";
        if search {
            let value = self.settings.get("SearchResultsSize");
            let pair = model::parse_pair(value, 'x').or_else(|| {
                let v: serde_json::Value = serde_json::from_str(value).ok()?;
                Some((v["width"].as_f64()? as f32, v["height"].as_f64()? as f32))
            });
            if let Some((w, h)) = pair {
                if w.is_finite() && h.is_finite() {
                    size = Vec2::new(w.max(600.0).min(primary.x), h.max(300.0).min(primary.y));
                }
            }
        }
        let mut position = Pos2::new(
            ((primary.x - size.x) / 2.0).max(0.0),
            ((primary.y - size.y) / 2.0).max(0.0),
        );
        let key = if search {
            "SearchResultsPosition"
        } else {
            "FavoritesManagerPos"
        };
        let saved = model::parse_pair(self.settings.get(key), ',').or_else(|| {
            let v: serde_json::Value = serde_json::from_str(self.settings.get(key)).ok()?;
            Some((v["x"].as_f64()? as f32, v["y"].as_f64()? as f32))
        });
        if let Some((x, y)) = saved {
            let p = Pos2::new(x, y);
            if desktop.contains_rect(Rect::from_min_size(p, size)) {
                position = p;
            }
        }
        egui::ViewportBuilder::default()
            .with_title(title)
            .with_inner_size(size)
            .with_min_inner_size(if search {
                [600.0, 300.0]
            } else {
                [440.0, 300.0]
            })
            .with_position(position)
    }
    fn dialogs(&mut self, ctx: &egui::Context) {
        if self.search_open {
            let builder =
                self.viewport_builder("搜索结果", "SearchResults", Vec2::new(950.0, 520.0));
            ctx.show_viewport_immediate(
                egui::ViewportId::from_hash_of("search_window"),
                builder,
                |ctx, _| {
                    if ctx.input(|i| {
                        i.viewport().close_requested() || i.key_pressed(egui::Key::Escape)
                    }) {
                        self.search_open = false;
                        self.search_cancel.store(true, Ordering::Relaxed);
                    }
                    self.remember_geometry(ctx, "SearchResults");
                    egui::CentralPanel::default().show(ctx, |ui| {
                        let root_name = self
                            .search_root
                            .file_name()
                            .map(|x| x.to_string_lossy().to_string())
                            .filter(|x| !x.is_empty())
                            .unwrap_or_else(|| "当前打开文件夹".into());
                        let keyword = if self.search_keyword.is_empty() {
                            "（空，列出全部图片）"
                        } else {
                            &self.search_keyword
                        };
                        ui.label(
                            RichText::new(format!(
                                "根目录：{root_name}（以下路径均相对此文件夹）\n关键词：{keyword}"
                            ))
                            .strong(),
                        );
                        ui.add_space(8.0);
                        let mut to_open = None;
                        let list_height = (ui.available_height() - 40.0).max(100.0);
                        egui::Frame::new()
                            .fill(Color32::WHITE)
                            .stroke(Stroke::new(1.0_f32, Color32::from_rgb(215, 224, 234)))
                            .inner_margin(4)
                            .show(ui, |ui| {
                                egui::ScrollArea::both()
                                    .auto_shrink([false, false])
                                    .max_height(list_height)
                                    .scroll_bar_visibility(
                                        egui::scroll_area::ScrollBarVisibility::AlwaysVisible,
                                    )
                                    .show_rows(ui, 22.0, self.results.len(), |ui, range| {
                                        for n in range {
                                            let path = &self.results[n];
                                            let label = path
                                                .strip_prefix(&self.search_root)
                                                .unwrap_or(path)
                                                .display()
                                                .to_string();
                                            let r = list_row(
                                                ui,
                                                RichText::new(&label),
                                                &label,
                                                self.result_selected == Some(n),
                                                22.0,
                                                true,
                                            );
                                            if r.clicked() {
                                                self.result_selected = Some(n);
                                                to_open = Some(path.clone());
                                            }
                                        }
                                    });
                            });
                        ui.add_space(6.0);
                        ui.label(RichText::new(&self.search_status).color(MUTED));
                        if !self.results.is_empty() {
                            let next = ctx.input(|i| {
                                if i.key_pressed(egui::Key::ArrowDown) {
                                    Some(
                                        self.result_selected
                                            .map(|n| (n + 1).min(self.results.len() - 1))
                                            .unwrap_or(0),
                                    )
                                } else if i.key_pressed(egui::Key::ArrowUp) {
                                    Some(
                                        self.result_selected
                                            .map(|n| n.saturating_sub(1))
                                            .unwrap_or(0),
                                    )
                                } else {
                                    None
                                }
                            });
                            if let Some(n) = next {
                                self.result_selected = Some(n);
                                to_open = Some(self.results[n].clone());
                            }
                            if ctx.input(|i| i.key_pressed(egui::Key::Enter)) {
                                if let Some(n) = self.result_selected {
                                    to_open = Some(self.results[n].clone());
                                }
                            }
                        }
                        if let Some(path) = to_open {
                            self.open_path(path, ctx);
                        }
                    });
                },
            );
        }
        if self.favorites_open {
            let builder =
                self.viewport_builder("收藏夹整理", "FavoritesManager", Vec2::new(640.0, 440.0));
            ctx.show_viewport_immediate(
                egui::ViewportId::from_hash_of("favorites_window"),
                builder,
                |ctx, _| {
                    if ctx.input(|i| {
                        i.viewport().close_requested() || i.key_pressed(egui::Key::Escape)
                    }) {
                        self.favorites_open = false;
                    }
                    ctx.input(|i| {
                        if let Some(rect) = i.viewport().outer_rect {
                            self.dirty |= self.settings.set(
                                "FavoritesManagerPos",
                                json!({"x":rect.min.x.round(),"y":rect.min.y.round()}),
                            );
                        }
                    });
                    egui::CentralPanel::default().show(ctx, |ui| {
                        egui::ScrollArea::both()
                            .auto_shrink([false, false])
                            .max_height((ui.available_height() - 48.0).max(80.0))
                            .show(ui, |ui| {
                                for (n, path) in self.draft.iter().enumerate() {
                                    let name = path
                                        .file_name()
                                        .unwrap_or(path.as_os_str())
                                        .to_string_lossy();
                                    if ui
                                        .selectable_label(
                                            self.draft_selected == Some(n),
                                            format!(
                                                "{} {name} ({})",
                                                if path.is_dir() { "📁" } else { "📄" },
                                                path.display()
                                            ),
                                        )
                                        .clicked()
                                    {
                                        self.draft_selected = Some(n);
                                    }
                                }
                            });
                        ui.separator();
                        ui.horizontal_wrapped(|ui| {
                            for (label, direction) in [("上移", -1isize), ("下移", 1)] {
                                if ui.button(label).clicked() {
                                    if let Some(n) = self.draft_selected {
                                        let next = n as isize + direction;
                                        if next >= 0 && (next as usize) < self.draft.len() {
                                            self.draft.swap(n, next as usize);
                                            self.draft_selected = Some(next as usize);
                                        }
                                    }
                                }
                            }
                            if ui
                                .button(
                                    RichText::new("删除").color(Color32::from_rgb(220, 76, 100)),
                                )
                                .clicked()
                                && self.draft_selected.is_some()
                            {
                                self.confirmation = Some(false);
                            }
                            if ui
                                .button(
                                    RichText::new("全部删除")
                                        .color(Color32::from_rgb(220, 76, 100)),
                                )
                                .clicked()
                                && !self.draft.is_empty()
                            {
                                self.confirmation = Some(true);
                            }
                            if ui.button("检查失效项目").clicked() {
                                let old = self.draft.len();
                                self.draft.retain(|p| p.exists());
                                self.draft_selected = None;
                                self.message = Some(if old == self.draft.len() {
                                    "没有发现失效的收藏项目".into()
                                } else {
                                    format!("已删除 {} 个失效的收藏项目", old - self.draft.len())
                                });
                            }
                            if ui
                                .add(
                                    egui::Button::new(RichText::new("确定").color(Color32::WHITE))
                                        .fill(BLUE),
                                )
                                .clicked()
                            {
                                self.favorites = self.draft.clone();
                                self.favorites_open = false;
                                self.persist();
                            }
                        });
                        if let Some(all) = self.confirmation {
                            egui::Window::new("确认")
                                .collapsible(false)
                                .resizable(false)
                                .anchor(egui::Align2::CENTER_CENTER, Vec2::ZERO)
                                .show(ctx, |ui| {
                                    ui.label(if all {
                                        "确定要删除所有收藏吗？"
                                    } else {
                                        "确定要删除选中的收藏吗？"
                                    });
                                    ui.horizontal(|ui| {
                                        if ui.button("是").clicked() {
                                            if all {
                                                self.draft.clear();
                                                self.favorites.clear();
                                                self.persist();
                                            } else if let Some(n) = self.draft_selected {
                                                if n < self.draft.len() {
                                                    self.draft.remove(n);
                                                }
                                            }
                                            self.draft_selected = None;
                                            self.confirmation = None;
                                        }
                                        if ui.button("否").clicked() {
                                            self.confirmation = None;
                                        }
                                    });
                                });
                        }
                    });
                },
            );
        }
        if self.help_open {
            ctx.show_viewport_immediate(
                egui::ViewportId::from_hash_of("help_window"),
                egui::ViewportBuilder::default()
                    .with_title("帮助与使用指南")
                    .with_minimize_button(false)
                    .with_maximize_button(false)
                    .with_position({
                        let (_, primary) = desktop_bounds();
                        [
                            (primary.x - 680.0).max(0.0) / 2.0,
                            (primary.y - 760.0).max(0.0) / 2.0,
                        ]
                    })
                    .with_inner_size([680.0, 760.0])
                    .with_min_inner_size([620.0, 520.0]),
                |ctx, _| {
                    if ctx.input(|i| {
                        i.viewport().close_requested() || i.key_pressed(egui::Key::Escape)
                    }) {
                        self.help_open = false;
                    }
                    if crate::help::show(ctx, self.help_reset_scroll) {
                        self.help_open = false;
                    }
                    self.help_reset_scroll = false;
                },
            );
        }
        if let Some(message) = self.message.clone() {
            let mut close = false;
            egui::Window::new("提示")
                .collapsible(false)
                .resizable(false)
                .anchor(egui::Align2::CENTER_CENTER, Vec2::ZERO)
                .show(ctx, |ui| {
                    ui.label(message);
                    if ui.button("确定").clicked() {
                        close = true;
                    }
                });
            if close {
                self.message = None;
            }
        }
    }
}
impl eframe::App for Viewer {
    fn update(&mut self, ctx: &egui::Context, _frame: &mut eframe::Frame) {
        // On Windows the initial client size can override WS_MAXIMIZE during creation.
        // Apply the original Tk startup behavior once after the native window exists.
        if self.maximize_on_start {
            self.maximize_on_start = false;
            ctx.send_viewport_cmd(egui::ViewportCommand::Maximized(false));
            ctx.send_viewport_cmd(egui::ViewportCommand::Maximized(true));
            ctx.request_repaint();
        }
        self.events(ctx);
        if !ctx.wants_keyboard_input()
            && !self.favorites_open
            && !self.help_open
            && self.image.is_some()
        {
            let mut change = 0.0;
            ctx.input(|i| {
                if i.key_pressed(egui::Key::Plus) {
                    change += 0.1;
                }
                if i.key_pressed(egui::Key::Minus) {
                    change -= 0.1;
                }
            });
            if change != 0.0 {
                self.scale = (self.scale + change).max(0.1);
                self.save_image();
                self.invalidate();
            }
        }
        self.toolbar(ctx);
        let panel = egui::SidePanel::left("directory_tree")
            .default_width(self.tree_width)
            .width_range(100.0..=ctx.content_rect().width() - 100.0)
            .resizable(true)
            .show(ctx, |ui| {
                if self.favorites_open || self.help_open {
                    ui.disable();
                }
                ui.add_space(5.0);
                ui.label(RichText::new("目录").strong());
                ui.separator();
                ui.spacing_mut().interact_size.y = 25.0;
                ui.spacing_mut().button_padding = Vec2::new(2.0, 0.0);
                egui::ScrollArea::vertical()
                    .auto_shrink([false, false])
                    .show(ui, |ui| {
                        for (path, label) in self.roots.clone() {
                            self.tree_node(ui, &path, &label, 0, ctx);
                        }
                    });
            });
        if (panel.response.rect.width() - self.tree_width).abs() > 0.5 {
            self.tree_width = panel.response.rect.width();
            self.dirty = true;
        }
        egui::CentralPanel::default()
            .frame(egui::Frame::new().fill(Color32::from_rgb(244, 240, 255)))
            .show(ctx, |ui| {
                if self.favorites_open || self.help_open {
                    ui.disable();
                }
                self.canvas(ui, ctx);
            });
        self.dialogs(ctx);
        if self.dirty && self.geometry_timer.elapsed() > Duration::from_millis(500) {
            self.persist();
            self.geometry_timer = std::time::Instant::now();
        }
        if self.loading || self.searching || !self.requested.is_empty() {
            ctx.request_repaint_after(Duration::from_millis(30));
        }
        if ctx.input(|i| i.viewport().close_requested()) {
            self.search_cancel.store(true, Ordering::Relaxed);
            self.save_image();
            self.persist();
        }
    }
    fn on_exit(&mut self, _gl: Option<&eframe::glow::Context>) {
        self.search_cancel.store(true, Ordering::Relaxed);
        self.generation.fetch_add(1, Ordering::Relaxed);
        self.save_image();
        self.persist();
    }
}
fn gradient(ui: &egui::Ui, rect: Rect) {
    let colors = [[244u8, 240, 255], [255, 249, 245], [255, 235, 221]];
    for n in 0..64 {
        let t = n as f32 / 63.0;
        let (a, b, f) = if t <= 0.5 {
            (colors[0], colors[1], t * 2.0)
        } else {
            (colors[1], colors[2], (t - 0.5) * 2.0)
        };
        let color = Color32::from_rgb(
            (a[0] as f32 + (b[0] as f32 - a[0] as f32) * f) as u8,
            (a[1] as f32 + (b[1] as f32 - a[1] as f32) * f) as u8,
            (a[2] as f32 + (b[2] as f32 - a[2] as f32) * f) as u8,
        );
        ui.painter().rect_filled(
            Rect::from_min_max(
                Pos2::new(rect.left(), rect.top() + rect.height() * n as f32 / 64.0),
                Pos2::new(
                    rect.right(),
                    rect.top() + rect.height() * (n + 1) as f32 / 64.0 + 1.0,
                ),
            ),
            0.0,
            color,
        );
    }
}
#[cfg(windows)]
fn drive_roots() -> Vec<(PathBuf, String)> {
    #[link(name = "kernel32")]
    unsafe extern "system" {
        fn GetLogicalDrives() -> u32;
        fn GetVolumeInformationW(
            root: *const u16,
            name: *mut u16,
            size: u32,
            serial: *mut u32,
            max_component: *mut u32,
            flags: *mut u32,
            fs_name: *mut u16,
            fs_size: u32,
        ) -> i32;
    }
    let mask = unsafe { GetLogicalDrives() };
    let mut result = Vec::new();
    for n in 0..26 {
        if mask & (1 << n) != 0 {
            let drive = format!("{}:\\", (b'A' + n) as char);
            let root: Vec<u16> = drive.encode_utf16().chain(Some(0)).collect();
            let mut label = [0u16; 261];
            // Removable or disconnected drives remain visible even without a label.
            let success = unsafe {
                GetVolumeInformationW(
                    root.as_ptr(),
                    label.as_mut_ptr(),
                    261,
                    std::ptr::null_mut(),
                    std::ptr::null_mut(),
                    std::ptr::null_mut(),
                    std::ptr::null_mut(),
                    0,
                )
            };
            let name = if success != 0 {
                String::from_utf16_lossy(&label[..label.iter().position(|c| *c == 0).unwrap_or(0)])
            } else {
                String::new()
            };
            let text = if name.is_empty() {
                drive.clone()
            } else {
                format!("{drive} ({name})")
            };
            result.push((PathBuf::from(drive), text));
        }
    }
    result
}
#[cfg(not(windows))]
fn drive_roots() -> Vec<(PathBuf, String)> {
    vec![(PathBuf::from("/"), "/".into())]
}
fn list_row(
    ui: &mut egui::Ui,
    text: RichText,
    label: &str,
    selected: bool,
    height: f32,
    grow: bool,
) -> egui::Response {
    let width = ui.available_width().max(1.0);
    let galley = egui::WidgetText::RichText(text.into()).into_galley(
        ui,
        Some(if grow {
            egui::TextWrapMode::Extend
        } else {
            egui::TextWrapMode::Truncate
        }),
        (width - 4.0).max(1.0),
        egui::TextStyle::Body,
    );
    let width = if grow {
        width.max(galley.size().x + 4.0)
    } else {
        width
    };
    let (rect, response) = ui.allocate_exact_size(Vec2::new(width, height), egui::Sense::click());
    if selected {
        ui.painter()
            .rect_filled(rect, 0.0, Color32::from_rgb(230, 240, 255));
    }
    let color = if selected {
        Color32::from_rgb(29, 78, 216)
    } else {
        Color32::from_rgb(30, 41, 59)
    };
    let position = rect.left_top() + Vec2::new(2.0, ((height - galley.size().y) / 2.0).max(0.0));
    ui.painter()
        .with_clip_rect(rect)
        .galley(position, galley, color);
    response.widget_info(|| {
        egui::WidgetInfo::selected(
            egui::WidgetType::SelectableLabel,
            ui.is_enabled(),
            selected,
            label,
        )
    });
    response
}
#[cfg(windows)]
fn desktop_bounds() -> (Rect, Vec2) {
    #[link(name = "user32")]
    unsafe extern "system" {
        fn GetSystemMetrics(index: i32) -> i32;
    }
    let get = |index| unsafe { GetSystemMetrics(index) } as f32;
    (
        Rect::from_min_size(Pos2::new(get(76), get(77)), Vec2::new(get(78), get(79))),
        Vec2::new(get(0), get(1)),
    )
}
#[cfg(not(windows))]
fn desktop_bounds() -> (Rect, Vec2) {
    (
        Rect::from_min_size(Pos2::ZERO, Vec2::new(1920.0, 1080.0)),
        Vec2::new(1920.0, 1080.0),
    )
}
