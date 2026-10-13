use std::{env, fs, path::PathBuf, process::Command};
fn main() {
    println!("cargo:rerun-if-changed=assets/icon.ico");
    println!("cargo:rerun-if-changed=build.rs");
    if env::var("CARGO_CFG_TARGET_OS").as_deref() != Ok("windows") {
        return;
    }
    let out = PathBuf::from(env::var_os("OUT_DIR").unwrap());
    fs::copy("assets/icon.ico", out.join("viewer.ico")).expect("无法复制图标");
    let rc = r#"
#pragma code_page(65001)
1 ICON "viewer.ico"
1 VERSIONINFO
FILEVERSION 2,0,0,0
PRODUCTVERSION 2,0,0,0
FILEFLAGSMASK 0x3fL
FILEFLAGS 0
FILEOS 0x40004L
FILETYPE 0x1L
FILESUBTYPE 0
BEGIN
 BLOCK "StringFileInfo"
 BEGIN
  BLOCK "080404B0"
  BEGIN
   VALUE "FileDescription", "乐谱 / 长图浏览器（Rust）\0"
   VALUE "ProductName", "图片分屏查看器\0"
   VALUE "FileVersion", "2.0.0.0\0"
   VALUE "ProductVersion", "2.0.0.0\0"
  END
 END
 BLOCK "VarFileInfo"
 BEGIN
  VALUE "Translation", 0x0804, 1200
 END
END
"#;
    fs::write(out.join("viewer.rc"), rc).unwrap();
    // GNU windres has ANSI absolute-path handling; all its arguments stay relative.
    let (tool, args, object) = if env::var("CARGO_CFG_TARGET_ENV").as_deref() == Ok("gnu") {
        (
            "windres.exe",
            vec![
                "--codepage=65001",
                "--input",
                "viewer.rc",
                "--output",
                "viewer.o",
                "--output-format=coff",
            ],
            "viewer.o",
        )
    } else {
        (
            "rc.exe",
            vec!["/nologo", "/c65001", "/fo", "viewer.res", "viewer.rc"],
            "viewer.res",
        )
    };
    let status = Command::new(tool)
        .current_dir(&out)
        .args(args)
        .status()
        .expect("找不到 Windows 资源编译器");
    assert!(status.success(), "Windows 图标资源编译失败");
    println!("cargo:rustc-link-arg={}", out.join(object).display());
}
