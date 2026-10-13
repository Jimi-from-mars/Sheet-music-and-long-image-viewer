#![windows_subsystem = "windows"]
mod help;
mod model;
mod viewer;
use eframe::egui;
fn main() -> eframe::Result {
    if let Ok(exe) = std::env::current_exe() {
        if let Some(dir) = exe.parent() {
            let _ = std::env::set_current_dir(dir);
        }
    }
    let icon = image::load_from_memory_with_format(
        include_bytes!("../assets/icon.png"),
        image::ImageFormat::Png,
    )
    .expect("内嵌图标损坏")
    .into_rgba8();
    let options = eframe::NativeOptions {
        viewport: egui::ViewportBuilder::default()
            .with_title("乐谱 / 长图浏览器")
            .with_inner_size([1280.0, 800.0])
            .with_min_inner_size([760.0, 480.0])
            .with_maximized(true)
            .with_icon(egui::IconData {
                width: icon.width(),
                height: icon.height(),
                rgba: icon.into_raw(),
            }),
        ..Default::default()
    };
    eframe::run_native(
        "图片分屏查看器",
        options,
        Box::new(|cc| Ok(Box::new(viewer::Viewer::new(cc)))),
    )
}
