# 构建 Rust 2.0

普通用户从项目 Releases 下载 Windows x64 ZIP，解压后双击 `图片分屏查看器_v2.0.exe`。不需要安装 Python、Pillow 或 Rust。

## Windows GNU 构建

需要安装 Rust 的 `x86_64-pc-windows-gnu` 工具链、MinGW-w64（包括 `windres.exe`）、LLVM（包括 `clang.exe` 和 `lld-link.exe`），并将这些工具加入 PATH。

```powershell
rustup target add x86_64-pc-windows-gnu
.\build.ps1 -Test
```

也可双击 `build.cmd`。首次构建会下载 Cargo 依赖，已有完整缓存时可使用 `.\build.ps1 -Test -Offline`。构建脚本保留调用者的 `CARGO_HOME`；项目本地 `.build/cargo` 缓存存在时优先使用该缓存。

正式文件输出到项目根目录，Cargo 中间产物在 `target/`。`.cargo` 的 LLVM 适配用于处理中文目录下 GNU 导入库和链接问题；辅助程序由构建脚本生成，无需预先下载。

## Windows MSVC 构建

也可以安装 Visual Studio Build Tools 的 C++ 桌面开发工具和 Windows SDK，在开发者终端执行：

```powershell
rustup target add x86_64-pc-windows-msvc
cargo test --locked --target x86_64-pc-windows-msvc
cargo build --locked --release --target x86_64-pc-windows-msvc
```

输出为 `target/x86_64-pc-windows-msvc/release/split-image-viewer.exe`。MSVC 路径未在本次发行中实际构建验证；已发布 EXE 使用 GNU/LLVM 构建。

## 源码和测试

- `src/main.rs`：程序入口；`src/viewer.rs`：窗口、目录和后台渲染。
- `src/model.rs`：配置、搜索、图片识别、分页逻辑及回归测试。
- `src/help.rs` 与 `assets/help.json`：帮助页布局和原文。
- `assets/icon.ico`、`assets/icon.png`：由原项目图标整理的嵌入资源。
- `validation/fixtures` 和 `validation/v1_2/fixtures`：人工生成的测试图片；文件名故意使用错误扩展名来验证按内容识别。

常规测试无需用户图库。被忽略的 `local_library_matches_pillow_dimensions` 是本地图库审计工具，需要自行提供 `validation/v1_2/image-inventory.json`；本仓库不包含用户图库或清单。

## 配置兼容

`setup.ini` 位于 EXE 所在目录；每个图片目录内的 `image_config.json` 保存缩放、重叠比例和排序。沿用 Python 版字段，并保留未知配置。若希望沿用旧设置，将新版放到旧程序旁边或复制旧 `setup.ini`。不会转换或改名原图片。

GIF 显示静态第一帧。目录和搜索仍沿用原版的 PNG、JPG、JPEG、GIF、BMP 扩展名筛选；实际解码按内容识别，可处理这些扩展名下保存的 WebP、TIFF 等内容。新增解码支持不代表目录筛选会显示所有格式的原生扩展名。
