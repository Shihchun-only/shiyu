# 发布 0.1.0

1. 将本项目源码上传到 `Shihchun-only/shiyu`，使用公开仓库、MIT 许可证。
2. 在 Windows 运行测试和 `tools/build_windows.py`。安装包、免安装包与 SHA256SUMS 均在 release/。
3. 检查无用户课程、资料库、真实密钥、私人截图和缓存音频进入 Git 或安装包。
4. 推送 `v0.1.0` 标签触发自动构建，生成 Draft Release。若工作流首次需要允许执行，由仓库所有者启用 Actions。
5. 校对 Draft Release 中的安装文件、校验值、更新说明后，公开发布。

也可直接新建 Release，附上已本地验证的安装程序、免安装包和 SHA256SUMS.txt。不需要将生成文件提交到 Git。

更新版本时同步：pyproject.toml、src/shiyu/__init__.py、tools/installer.py、tools/build_windows.py、CHANGELOG 和 README 的文件名。升级应保留 `%LOCALAPPDATA%\Shiyu`；资料结构变动应先备份。

本版本未做代码签名，公开发行前可增加签名证书和工作流签名步骤。当前构建流程不需要任何第三方密钥，GitHub Release 只使用该仓库的短期 GITHUB_TOKEN。
