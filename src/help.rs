use eframe::egui::{self, Color32, RichText, Stroke, Vec2};
use serde_json::Value;
use std::sync::OnceLock;
const TEXT: Color32 = Color32::from_rgb(30, 41, 59);
const MUTED: Color32 = Color32::from_rgb(100, 116, 139);
const BG: Color32 = Color32::from_rgb(244, 247, 251);
const SOFT: Color32 = Color32::from_rgb(248, 250, 252);
const BORDER: Color32 = Color32::from_rgb(226, 232, 240);
fn data() -> &'static Value {
    static DATA: OnceLock<Value> = OnceLock::new();
    DATA.get_or_init(|| {
        serde_json::from_str(include_str!("../assets/help.json"))
            .expect("invalid original help structure")
    })
}
fn string(v: &Value) -> &str {
    v.as_str().unwrap_or("")
}
fn text(key: &str) -> &'static str {
    string(&data()["texts"][key])
}
fn label(ui: &mut egui::Ui, text: &str, size: f32, color: Color32, bold: bool) {
    let rich = RichText::new(text)
        .font(egui::FontId::new(
            size,
            egui::FontFamily::Name(if bold { "HelpBold" } else { "HelpRegular" }.into()),
        ))
        .color(color);
    // Tk Labels include two pixels of vertical padding on each side.
    egui::Frame::new()
        .inner_margin(egui::Margin::symmetric(0, 2))
        .show(ui, |ui| {
            ui.add(egui::Label::new(rich).wrap());
        });
}
fn box_frame(fill: Color32, border: Color32, x: i8, y: i8) -> egui::Frame {
    egui::Frame::new()
        .fill(fill)
        .stroke(Stroke::new(1.0_f32, border))
        .inner_margin(egui::Margin::symmetric(x, y))
        .corner_radius(0)
}
fn chip(ui: &mut egui::Ui, text: &str, fill: Color32, color: Color32, border: Color32) {
    box_frame(fill, border, 7, 2).show(ui, |ui| label(ui, text, 10.7, color, true));
}
fn card(
    ui: &mut egui::Ui,
    title: &str,
    icon: &str,
    tip: &str,
    contents: impl FnOnce(&mut egui::Ui),
) {
    box_frame(Color32::WHITE, Color32::from_rgb(215, 224, 234), 18, 14).show(ui, |ui| {
        ui.set_width(ui.available_width());
        ui.horizontal(|ui| {
            label(ui, icon, 14.7, TEXT, false);
            label(ui, title, 13.3, TEXT, true);
            ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                label(ui, tip, 10.7, MUTED, false)
            });
        });
        ui.add_space(6.0);
        ui.separator();
        ui.add_space(6.0);
        contents(ui);
    });
    ui.add_space(12.0);
}
fn points(ui: &mut egui::Ui, name: &str, colors: &[Color32], symbol: &str) {
    for (n, row) in data()[name].as_array().unwrap().iter().enumerate() {
        ui.horizontal_top(|ui| {
            label(ui, symbol, 12.0, colors[n % colors.len()], true);
            ui.vertical(|ui| {
                label(ui, string(&row[0]), 12.0, TEXT, true);
                ui.add_space(1.0);
                label(ui, string(&row[1]), 10.7, MUTED, false);
            });
        });
        ui.add_space(7.0);
    }
}
pub fn show(ctx: &egui::Context, reset_scroll: bool) -> bool {
    let mut close = false;
    egui::TopBottomPanel::bottom("help_footer")
        .frame(box_frame(
            Color32::WHITE,
            Color32::from_rgb(215, 224, 234),
            20,
            10,
        ))
        .show(ctx, |ui| {
            ui.horizontal(|ui| {
                label(ui, text("tip_icon"), 10.7, MUTED, false);
                chip(
                    ui,
                    "Esc",
                    Color32::from_rgb(241, 245, 249),
                    TEXT,
                    Color32::from_rgb(203, 213, 225),
                );
                label(ui, text("tip_tail"), 10.7, MUTED, false);
                ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                    if ui
                        .add_sized(
                            [110.0, 31.0],
                            egui::Button::new(
                                RichText::new(text("ok_button"))
                                    .size(13.3)
                                    .color(Color32::WHITE),
                            )
                            .fill(Color32::from_rgb(37, 99, 235))
                            .corner_radius(12),
                        )
                        .clicked()
                    {
                        close = true;
                    }
                });
            });
        });
    egui::CentralPanel::default()
        .frame(egui::Frame::new().fill(BG))
        .show(ctx, |ui| {
            ui.spacing_mut().item_spacing = Vec2::new(6.0, 0.0);
            let mut scroll = egui::ScrollArea::vertical()
                .id_salt("original_help_scroll")
                .auto_shrink([false, false]);
            if reset_scroll {
                scroll = scroll.vertical_scroll_offset(0.0);
            }
            scroll.show(ui, |ui| {
                egui::Frame::new()
                    .inner_margin(egui::Margin::symmetric(18, 16))
                    .show(ui, |ui| {
                        ui.set_width(ui.available_width());
                        box_frame(Color32::WHITE, Color32::from_rgb(215, 224, 234), 18, 16).show(
                            ui,
                            |ui| {
                                ui.set_width(ui.available_width());
                                ui.horizontal(|ui| {
                                    label(ui, text("logo_label"), 21.3, TEXT, false);
                                    label(ui, text("title_label"), 17.3, TEXT, true);
                                    chip(
                                        ui,
                                        text("badge_lbl"),
                                        Color32::from_rgb(219, 234, 254),
                                        Color32::from_rgb(29, 78, 216),
                                        Color32::from_rgb(219, 234, 254),
                                    );
                                });
                                ui.add_space(4.0);
                                label(ui, text("subtitle_label"), 12.0, MUTED, false);
                                ui.add_space(10.0);
                                ui.horizontal(|ui| {
                                    for (title, bg, fg, border) in [
                                        (
                                            "⚡ 智能等分切分",
                                            [224, 242, 254],
                                            [3, 105, 161],
                                            [186, 230, 253],
                                        ),
                                        (
                                            "🔶 橙色接缝引导",
                                            [255, 237, 213],
                                            [194, 65, 12],
                                            [254, 215, 170],
                                        ),
                                        (
                                            "🟢 青绿定位遮罩",
                                            [204, 251, 241],
                                            [15, 118, 110],
                                            [153, 246, 228],
                                        ),
                                        (
                                            "💾 双层状态记忆",
                                            [243, 232, 255],
                                            [126, 34, 206],
                                            [233, 213, 255],
                                        ),
                                    ] {
                                        chip(
                                            ui,
                                            title,
                                            Color32::from_rgb(bg[0], bg[1], bg[2]),
                                            Color32::from_rgb(fg[0], fg[1], fg[2]),
                                            Color32::from_rgb(border[0], border[1], border[2]),
                                        );
                                    }
                                });
                                ui.add_space(10.0);
                                box_frame(SOFT, BORDER, 12, 10).show(ui, |ui| {
                                    ui.set_width(ui.available_width());
                                    label(ui, string(&data()["intro_text"]), 12.0, TEXT, false);
                                });
                            },
                        );
                        ui.add_space(12.0);
                        card(
                            ui,
                            "快捷键与操作速查",
                            "⚡",
                            "核心高频交互",
                            |ui| {
                                for row in data()["shortcuts_list"].as_array().unwrap() {
                                    box_frame(SOFT, BORDER, 10, 8).show(ui, |ui| {
                                        ui.set_width(ui.available_width());
                                        ui.horizontal(|ui| {
                                            ui.horizontal(|ui| {
                                                for (n, key) in
                                                    row[0].as_array().unwrap().iter().enumerate()
                                                {
                                                    if n > 0 {
                                                        label(ui, "+", 10.7, MUTED, true);
                                                    }
                                                    chip(
                                                        ui,
                                                        string(key),
                                                        Color32::WHITE,
                                                        TEXT,
                                                        Color32::from_rgb(203, 213, 225),
                                                    );
                                                }
                                                if !row[1].is_null() {
                                                    label(ui, string(&row[1]), 10.7, MUTED, false);
                                                }
                                            });
                                            ui.add_space(8.0);
                                            ui.vertical(|ui| {
                                                label(ui, string(&row[2]), 12.0, TEXT, true);
                                                ui.add_space(2.0);
                                                label(ui, string(&row[3]), 10.7, MUTED, false);
                                            });
                                        });
                                    });
                                    ui.add_space(6.0);
                                }
                            },
                        );
                        card(
                            ui,
                            "智能切分与接缝引导",
                            "🎼",
                            "多页无缝并排",
                            |ui| {
                                points(
                                    ui,
                                    "split_points",
                                    &[
                                        Color32::from_rgb(37, 99, 235),
                                        Color32::from_rgb(249, 115, 22),
                                        Color32::from_rgb(15, 159, 145),
                                    ],
                                    "●",
                                )
                            },
                        );
                        card(
                            ui,
                            "收藏夹与文件管理",
                            "⭐",
                            "高效曲目整理",
                            |ui| points(ui, "fav_points", &[Color32::from_rgb(220, 38, 38)], "•"),
                        );
                        card(
                            ui,
                            "双层智能记忆机制",
                            "💾",
                            "自动持久化",
                            |ui| {
                                ui.columns(2, |cols| {
                                    for (column, title, desc) in [
                                        (0, "ini_title", "ini_desc"),
                                        (1, "json_title", "json_desc"),
                                    ] {
                                        box_frame(SOFT, BORDER, 12, 10).show(
                                            &mut cols[column],
                                            |ui| {
                                                ui.set_width(ui.available_width());
                                                ui.set_min_height(130.0);
                                                label(ui, text(title), 12.0, TEXT, true);
                                                ui.add_space(4.0);
                                                label(ui, text(desc), 10.7, MUTED, false);
                                            },
                                        );
                                    }
                                });
                            },
                        );
                        box_frame(
                            Color32::from_rgb(239, 246, 255),
                            Color32::from_rgb(191, 219, 254),
                            16,
                            12,
                        )
                        .show(ui, |ui| {
                            ui.set_width(ui.available_width());
                            ui.vertical_centered(|ui| {
                                label(
                                    ui,
                                    text("fun_title"),
                                    13.3,
                                    Color32::from_rgb(29, 78, 216),
                                    true,
                                );
                                ui.add_space(2.0);
                                label(
                                    ui,
                                    text("fun_text"),
                                    10.7,
                                    Color32::from_rgb(71, 85, 105),
                                    false,
                                );
                            });
                        });
                    });
            });
        });
    close
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn original_help_groups_are_preserved() {
        assert_eq!(data()["shortcuts_list"].as_array().unwrap().len(), 6);
        assert_eq!(data()["shortcuts_list"][1][0][0], "Ctrl");
        assert_eq!(data()["split_points"].as_array().unwrap().len(), 3);
        assert_eq!(data()["fav_points"].as_array().unwrap().len(), 3);
        assert_eq!(text("ok_button"), "我知道了");
        assert!(text("json_title").contains("image_config.json"));
    }
}
