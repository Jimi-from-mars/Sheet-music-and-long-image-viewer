use serde_json::{Value, json};
use std::{
    collections::BTreeMap,
    fs,
    path::{Path, PathBuf},
    sync::atomic::{AtomicBool, Ordering},
    time::SystemTime,
};
use unicode_casefold::UnicodeCaseFold;
pub const EXTENSIONS: &[&str] = &["png", "jpg", "jpeg", "gif", "bmp"];
/// Pillow-compatible format detection: extensions may not match the encoded bytes.
pub fn load_image(path: &Path) -> Result<image::DynamicImage, String> {
    image::ImageReader::open(path)
        .map_err(|e| e.to_string())?
        .with_guessed_format()
        .map_err(|e| e.to_string())?
        .decode()
        .map_err(|e| e.to_string())
}
pub fn reserve_page(
    pending: &mut std::collections::HashSet<u32>,
    task_generation: u64,
    current_generation: u64,
    page: u32,
) -> bool {
    task_generation == current_generation && pending.insert(page)
}
pub fn is_image(path: &Path) -> bool {
    path.extension()
        .is_some_and(|x| EXTENSIONS.contains(&x.to_string_lossy().to_lowercase().as_str()))
}
pub fn parse_pair(text: &str, separator: char) -> Option<(f32, f32)> {
    let (a, b) = text.split_once(separator)?;
    let (a, b) = (a.trim().parse::<f32>().ok()?, b.trim().parse::<f32>().ok()?);
    (a.is_finite() && b.is_finite()).then_some((a, b))
}
pub fn read_json(path: &Path) -> Value {
    fs::read_to_string(path)
        .ok()
        .and_then(|s| serde_json::from_str(&s).ok())
        .filter(Value::is_object)
        .unwrap_or_else(|| json!({}))
}
pub fn write_json(path: &Path, value: &Value) -> Result<(), String> {
    fs::write(
        path,
        serde_json::to_string_pretty(value).map_err(|e| e.to_string())?,
    )
    .map_err(|e| format!("无法保存 {}：{}", path.display(), e))
}
#[derive(Default)]
pub struct Settings {
    pub values: BTreeMap<String, String>,
}
impl Settings {
    pub fn load() -> Self {
        Self::from_text(&fs::read_to_string("setup.ini").unwrap_or_default())
    }
    pub fn from_text(text: &str) -> Self {
        let mut values = BTreeMap::new();
        for line in text.trim_start_matches('\u{feff}').lines() {
            if let Some((k, v)) = line.split_once('=') {
                values.insert(k.trim().to_owned(), v.trim().to_owned());
            }
        }
        Self { values }
    }
    pub fn get(&self, key: &str) -> &str {
        self.values.get(key).map(String::as_str).unwrap_or("")
    }
    pub fn set(&mut self, key: &str, value: impl ToString) -> bool {
        let value = value.to_string();
        if self.values.get(key) == Some(&value) {
            return false;
        }
        self.values.insert(key.to_owned(), value);
        true
    }
    pub fn save(&self) -> Result<(), String> {
        let text = self
            .values
            .iter()
            .map(|(k, v)| format!("{k}={v}\n"))
            .collect::<String>();
        fs::write("setup.ini", text).map_err(|e| format!("无法保存 setup.ini：{e}"))
    }
    pub fn favorites(&self) -> Vec<PathBuf> {
        serde_json::from_str::<Vec<String>>(self.get("Favorites"))
            .unwrap_or_default()
            .into_iter()
            .map(PathBuf::from)
            .collect()
    }
}
pub fn image_settings(file: &Path) -> (f64, f64) {
    let config = read_json(
        &file
            .parent()
            .unwrap_or(Path::new("."))
            .join("image_config.json"),
    );
    let value = &config[file
        .file_name()
        .unwrap_or_default()
        .to_string_lossy()
        .as_ref()];
    (
        value["scale"]
            .as_f64()
            .filter(|x| x.is_finite() && *x >= 0.1)
            .unwrap_or(1.0),
        value["overlap_ratio"]
            .as_f64()
            .filter(|x| x.is_finite())
            .unwrap_or(0.2)
            .clamp(0.05, 0.3),
    )
}
pub fn save_image_settings(file: &Path, scale: f64, overlap: f64) -> Result<(), String> {
    let path = file
        .parent()
        .unwrap_or(Path::new("."))
        .join("image_config.json");
    let mut config = read_json(&path);
    config[file
        .file_name()
        .unwrap_or_default()
        .to_string_lossy()
        .as_ref()] = json!({"scale":scale,"overlap_ratio":overlap});
    write_json(&path, &config)
}
pub fn search_images(
    root: &Path,
    query: &str,
    recursive: bool,
    cancel: &AtomicBool,
    mut on_found: impl FnMut(PathBuf),
) -> (usize, usize) {
    let query = query.trim().case_fold().collect::<String>();
    let mut count = 0;
    let mut errors = 0;
    let walker = walkdir::WalkDir::new(root)
        .follow_links(false)
        .max_depth(if recursive { usize::MAX } else { 1 });
    for entry in walker {
        if cancel.load(Ordering::Relaxed) {
            break;
        }
        match entry {
            Ok(entry) if is_image(entry.path()) && entry.path().is_file() => {
                let relative = entry
                    .path()
                    .strip_prefix(root)
                    .unwrap_or(entry.path())
                    .to_string_lossy()
                    .case_fold()
                    .collect::<String>();
                if relative.contains(&query) {
                    count += 1;
                    on_found(entry.path().to_owned());
                }
            }
            Err(_) => errors += 1,
            _ => {}
        }
    }
    (count, errors)
}
#[derive(Clone, Debug)]
pub struct Entry {
    pub path: PathBuf,
    pub directory: bool,
    pub modified: SystemTime,
}
pub fn entries(dir: &Path) -> Vec<Entry> {
    let method = read_json(&dir.join("image_config.json"))["sort_method"]
        .as_str()
        .unwrap_or("name_asc")
        .to_owned();
    let mut result = Vec::new();
    if let Ok(items) = fs::read_dir(dir) {
        for item in items.flatten() {
            let path = item.path();
            if let Ok(meta) = item.metadata() {
                if meta.is_dir() || is_image(&path) {
                    result.push(Entry {
                        path,
                        directory: meta.is_dir(),
                        modified: meta.modified().unwrap_or(SystemTime::UNIX_EPOCH),
                    });
                }
            }
        }
    }
    result.sort_by(|a, b| {
        let names = || {
            a.path
                .file_name()
                .unwrap_or_default()
                .to_string_lossy()
                .to_lowercase()
                .cmp(
                    &b.path
                        .file_name()
                        .unwrap_or_default()
                        .to_string_lossy()
                        .to_lowercase(),
                )
        };
        b.directory
            .cmp(&a.directory)
            .then_with(|| match method.as_str() {
                "time_desc" => b.modified.cmp(&a.modified).then_with(names),
                "time_asc" => a.modified.cmp(&b.modified).then_with(names),
                "name_desc" => names().reverse(),
                _ => names(),
            })
    });
    result
}
pub fn page_geometry(
    width: u32,
    height: u32,
    scale: f64,
    canvas_height: u32,
    overlap: f64,
) -> (u32, u32, u32, u32) {
    let width = ((width as f64 * scale) as u32).max(1);
    let height = ((height as f64 * scale) as u32).max(1);
    if height <= canvas_height {
        return (width, height, 1, width);
    }
    let effective = canvas_height
        .saturating_sub((canvas_height as f64 * overlap) as u32)
        .max(1);
    (width, effective, height.div_ceil(effective), width + 20)
}

pub fn render_page(
    image: &image::DynamicImage,
    width: u32,
    height: u32,
    canvas: u32,
    step: u32,
    page: u32,
    split: bool,
) -> image::RgbaImage {
    let start = page * step;
    let page_height = if split {
        canvas.min(height - start)
    } else {
        height
    };
    let top = (start as f64 * image.height() as f64 / height as f64).floor() as u32;
    let bottom = (((start + page_height) as f64 * image.height() as f64 / height as f64).ceil()
        as u32)
        .min(image.height());
    image
        .crop_imm(0, top, image.width(), bottom.saturating_sub(top).max(1))
        .resize_exact(width, page_height, image::imageops::FilterType::Lanczos3)
        .into_rgba8()
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn stale_page_requests_do_not_block_new_generation() {
        let mut pending = std::collections::HashSet::new();
        assert!(reserve_page(&mut pending, 1, 1, 0));
        pending.clear(); // overlap change invalidates generation 1
        assert!(!reserve_page(&mut pending, 1, 2, 0)); // old frame must not reserve page 0
        assert!(reserve_page(&mut pending, 2, 2, 0));
        assert!(!reserve_page(&mut pending, 2, 2, 0));
        for generation in 3..=40 {
            pending.clear();
            assert!(!reserve_page(&mut pending, generation - 1, generation, 0));
            assert!(reserve_page(&mut pending, generation, generation, 0));
        }
    }
    #[test]
    fn pagination_matches_python() {
        assert_eq!(page_geometry(600, 2500, 1.0, 1000, 0.2), (600, 800, 4, 620));
        assert_eq!(page_geometry(600, 800, 1.0, 1000, 0.2), (600, 800, 1, 600));
        assert_eq!(
            page_geometry(600, 1001, 1.0, 1000, 0.05),
            (600, 950, 2, 620)
        );
    }
    #[test]
    fn supported_formats() {
        for x in ["a.PNG", "a.JpEg", "a.gif", "a.bmp"] {
            assert!(is_image(Path::new(x)));
        }
        assert!(!is_image(Path::new("a.webp")));
    }
    #[test]
    fn original_search_window_geometry_formats() {
        assert_eq!(parse_pair("950x520", 'x'), Some((950.0, 520.0)));
        assert_eq!(parse_pair("-1920,200", ','), Some((-1920.0, 200.0)));
        assert_eq!(parse_pair("NaN,200", ','), None);
        assert_eq!(parse_pair("invalid", 'x'), None);
    }
    fn fixture(name: &str) -> PathBuf {
        let path = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("validation/unit")
            .join(name);
        fs::create_dir_all(&path).unwrap();
        path
    }
    #[test]
    fn python_config_fields_and_unicode_paths_roundtrip() {
        let mut config = Settings::from_text(
            "TreeWidth=240\r\nFavorites=[\"F:\\\\图片 (练习)\\\\曲谱.png\"]\r\nUnknown=a=b\r\n",
        );
        assert_eq!(config.get("TreeWidth"), "240");
        assert_eq!(config.get("Unknown"), "a=b");
        assert_eq!(
            config.favorites(),
            vec![PathBuf::from("F:\\图片 (练习)\\曲谱.png")]
        );
        assert!(!config.set("TreeWidth", 240));
        assert!(config.set("TreeWidth", 260));
        let dir = fixture("configuration");
        let file = dir.join("曲谱 (1).png");
        let path = dir.join("image_config.json");
        write_json(&path,&json!({"sort_method":"time_desc","other.png":{"scale":2.0,"overlap_ratio":0.1},"unknown":{"data":123}})).unwrap();
        save_image_settings(&file, 1.3, 0.25).unwrap();
        assert_eq!(image_settings(&file), (1.3, 0.25));
        let saved = read_json(&path);
        assert_eq!(saved["sort_method"], "time_desc");
        assert_eq!(saved["other.png"]["scale"], 2.0);
        assert_eq!(saved["unknown"]["data"], 123);
        assert_eq!(image_settings(&dir.join("new.png")), (1.0, 0.2));
    }
    #[test]
    fn sorting_directories_first_in_all_four_modes() {
        let dir = fixture("sorting");
        fs::create_dir_all(dir.join("folder")).unwrap();
        for (name, time) in [("A.png", 10), ("z.JPG", 20)] {
            let file = fs::File::create(dir.join(name)).unwrap();
            file.set_times(
                fs::FileTimes::new()
                    .set_modified(SystemTime::UNIX_EPOCH + std::time::Duration::from_secs(time)),
            )
            .unwrap();
        }
        fs::write(dir.join("not-an-image.txt"), "ignored").unwrap();
        for (method, first) in [
            ("name_asc", "A.png"),
            ("name_desc", "z.JPG"),
            ("time_asc", "A.png"),
            ("time_desc", "z.JPG"),
        ] {
            write_json(
                &dir.join("image_config.json"),
                &json!({"sort_method":method}),
            )
            .unwrap();
            let items = entries(&dir);
            assert_eq!(items.len(), 3);
            assert!(items[0].directory);
            assert_eq!(items[1].path.file_name().unwrap(), first);
        }
    }
    #[test]
    fn recursive_search_relative_paths_unicode_casefold_and_stop() {
        let dir = fixture("search");
        fs::create_dir_all(dir.join("Nested")).unwrap();
        for name in ["Straße.PNG", "normal.jpg", "ignore.txt", "Nested/score.bmp"] {
            fs::write(dir.join(name), "fixture").unwrap();
        }
        let cancel = AtomicBool::new(false);
        let mut paths = Vec::new();
        assert_eq!(
            search_images(&dir, "", false, &cancel, |p| paths.push(p)),
            (2, 0)
        );
        assert_eq!(
            search_images(&dir, "STRASSE", true, &cancel, |_| {}),
            (1, 0)
        );
        assert_eq!(search_images(&dir, "nested", true, &cancel, |_| {}), (1, 0));
        assert_eq!(
            search_images(&dir, "no match", true, &cancel, |_| {}),
            (0, 0)
        );
        cancel.store(true, Ordering::Relaxed);
        assert_eq!(
            search_images(&dir, "", true, &cancel, |_| panic!("must stop")),
            (0, 0)
        );
        cancel.store(false, Ordering::Relaxed);
        assert!(search_images(&dir.join("missing"), "", true, &cancel, |_| {}).1 > 0);
    }
    #[test]
    fn long_image_overlap_and_last_page_pixels() {
        let source =
            image::DynamicImage::ImageRgba8(image::RgbaImage::from_fn(60, 2500, |x, y| {
                image::Rgba([x as u8, (y % 251) as u8, 0, 255])
            }));
        let first = render_page(&source, 60, 2500, 1000, 800, 0, true);
        let second = render_page(&source, 60, 2500, 1000, 800, 1, true);
        let last = render_page(&source, 60, 2500, 1000, 800, 3, true);
        assert_eq!(last.dimensions(), (60, 100));
        for y in 0..200 {
            assert_eq!(first.get_pixel(5, 800 + y), second.get_pixel(5, y));
        }
        assert_eq!(last.get_pixel(5, 0), source.to_rgba8().get_pixel(5, 2400));
        assert_eq!(
            render_page(&source, 30, 500, 1000, 500, 0, false).dimensions(),
            (30, 500)
        );
    }
    #[test]
    fn image_decoders_and_invalid_input() {
        let dir = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("validation/fixtures");
        for file in ["long.png", "short.jpg", "short.gif", "short.bmp"] {
            let image = image::ImageReader::open(dir.join(file))
                .unwrap()
                .decode()
                .unwrap();
            assert!(image.width() > 0 && image.height() > 0);
        }
        assert!(
            image::ImageReader::open(dir.join("corrupt.png"))
                .unwrap()
                .decode()
                .is_err()
        );
    }
    #[test]
    fn image_content_overrides_misleading_extension() {
        let dir = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("validation/v1_2/fixtures");
        for format in ["png", "jpeg", "gif", "bmp", "webp", "tiff", "ppm", "qoi"] {
            let decoded = load_image(&dir.join(format!("{format}.jpg"))).unwrap();
            assert_eq!((decoded.width(), decoded.height()), (31, 47), "{format}");
        }
        assert!(load_image(&dir.join("../../fixtures/corrupt.png")).is_err());
    }
    #[test]
    #[ignore = "local user library audit; run explicitly"]
    fn local_library_matches_pillow_dimensions() {
        let inventory = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("validation/v1_2/image-inventory.json");
        let rows: Vec<Value> = serde_json::from_slice(&fs::read(inventory).unwrap()).unwrap();
        let mut failures = Vec::new();
        for row in &rows {
            let path = Path::new(row["path"].as_str().unwrap());
            match load_image(path) {
                Ok(image) if image.width() as u64 == row["size"][0].as_u64().unwrap()
                    && image.height() as u64 == row["size"][1].as_u64().unwrap() => {},
                result => failures.push(format!("{}: {:?}", path.display(), result.map(|i| (i.width(), i.height())))),
            }
        }
        assert!(failures.is_empty(), "{}", failures.join("\n"));
        println!("Verified {} images against Pillow dimensions", rows.len());
    }
}
