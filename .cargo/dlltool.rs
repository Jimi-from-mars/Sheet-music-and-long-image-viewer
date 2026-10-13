// LLVM import-library adapter for Rust GNU builds in Unicode directories.
use std::{env,fs,path::PathBuf,process::{Command,exit}};
fn main(){
    let args:Vec<String>=env::args().skip(1).collect();
    let value=|flag:&str|args.iter().position(|s|s==flag).and_then(|i|args.get(i+1)).cloned().unwrap_or_default();
    let def=PathBuf::from(value("-d"));let output=value("-l");let name=value("-D");
    if output.is_empty()||name.is_empty(){eprintln!("invalid DLL import arguments");exit(1);}
    let text=fs::read_to_string(&def).expect("read import definitions");
    let llvm_def=def.with_extension("llvm.def");
    fs::write(&llvm_def,format!("LIBRARY {name}\n{text}")).expect("write LLVM definitions");
    let status=Command::new("lld-link.exe").args(["/lib","/machine:x64",&format!("/def:{}",llvm_def.display()),&format!("/out:{output}")]).status().expect("LLVM lld-link not found");
    exit(status.code().unwrap_or(1));
}
