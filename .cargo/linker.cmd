@echo off
clang.exe --target=x86_64-w64-windows-gnu -fuse-ld=lld %*
