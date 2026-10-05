# 拾语 Shiyu

把分类课件变成可以点击听音、查词、修改和打印的法语学习资料。Windows 本地应用，界面在浏览器显示，课程与音频保存在电脑里。

**当前版本：0.1.0（公开测试版），支持 Windows 10 / 11 x64。**

## 安装

在 [Releases](https://github.com/Shihchun-only/shiyu/releases) 下载 `Shiyu-0.1.0-windows-x64-setup.exe`。运行后点击“安装拾语”，再通过桌面或开始菜单打开。无需安装 Python，也无需管理员权限。

喜欢免安装方式，可以下载 `Shiyu-0.1.0-windows-x64-portable.zip`，完整解压后双击 `Shiyu.exe`；请保留 `_internal` 文件夹。

发布文件附 `SHA256SUMS.txt`，可用 PowerShell 的 `Get-FileHash` 核对。当前版本没有代码签名，Windows 可能显示发行者未验证；请先确认文件来自本仓库 Releases。

## 开始学习

1. 打开自制示例课件，或导入自己准备的分类 PDF / `.course.json`。
2. 首次联网点击“处理未完成内容”，获取 Larousse 法英词条的短释义与官方音频。完成一个词立即保存一个。
3. 点击法语词自动播放本地发音，显示词形、音标、词性及词典短摘录。
4. 随时填写中文解释、修改原形和释义、导入个人音频、保存笔记与收藏。
5. 打印与导出支持白底紧凑 A4 讲义、自测答案、原图分类 PDF 和分类 JSON。

PDF 必须包含本软件支持的隐藏分类数据。普通扫描 PDF 和直接截图不能自动导入分析。制作方法见 [分类课件规范](docs/classification-format.md)。本仓库自制示例可自由使用。

## 资料在哪里

默认在 `%LOCALAPPDATA%\Shiyu`：课程、词典缓存、实际音频、收藏和个人修改使用同一资料库。更新应用不会覆盖它，卸载应用也会保留它。

软件只监听本机地址。关闭浏览器后后台服务仍运行；要退出，请使用“设置与备份 → 退出本地服务”。重复打开会复用已有服务。

“导出完整备份”包含图片、音频、词义、修改和笔记。恢复前自动保存一份当前资料备份。导出文件还会保存在资料库的 `exports` 文件夹，可以在设置中直接打开。

旧本机版迁移：先从旧版导出完整备份，再在新版“设置与备份 → 从备份恢复”。备份不包含 API 密钥，迁移后需要自行配置。

## 词典与 AI 的范围

- 显示 Larousse 法英词典的核心英文短摘录，附完整官方词条链接；不会发布或预装其词义库及音频库。
- 音频来自词条上的官方发音按钮，保存完整音频文件，之后可离线播放。变形没有对应音频时会明确提示播放原形。
- 多义词默认首个分类，支持手动更换词性/发音。基本词形候选不能替代语境判断，“待核对”内容需要人工检查。
- 中文来自课件、个人修订或可选 AI，不冒充 Larousse 中文释义。
- 可选 AI 默认关闭。启用前须配置兼容 Chat Completions 的 HTTPS 地址、模型和密钥，并同意将单词、上下文与课件中文发送到该服务。服务可能收费。密钥用 Windows 当前用户加密，不进入备份。

Larousse 网站结构和可访问性可能变化，新词获取可能失败；失败会明确显示，可以重试或手动补充，已保存资料仍可使用。请遵守所访问服务的使用规则以及自己课程材料的授权范围。

## 开发与打包

Python 3.12+，正式 Windows 打包使用 Python 3.14 x64。

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements-build.txt
.\.venv\Scripts\python -m pip install -e . --no-deps
.\.venv\Scripts\python -m unittest discover -s tests -v
.\.venv\Scripts\python tools/build_windows.py
```

源码启动：`python -m shiyu`（先安装 editable package）。生成文件位于 `release/`。

GitHub Actions 对推送执行测试。推送 `v0.1.0` 标签后自动构建安装版和免安装版并创建 Draft Release，维护者检查后公开发布。请遵循 [发布说明](docs/releasing.md)。

## 反馈和贡献

在 Issues 描述复现步骤、Windows 版本、拾语版本与错误提示。不要公开上传个人课程、数据库、API 密钥或完整备份。诊断文件位于资料目录的 `startup-error.log`，发布前检查是否含个人路径。

欢迎小范围修复和改进。详见 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 许可证

软件代码与自制示例采用 MIT。DejaVu 字体、Python 及其他组件保留各自许可证，见 `third-party-notices/` 与 `src/shiyu/assets/DejaVuSans-LICENSE.txt`。Larousse 内容与用户课件不受本仓库 MIT 许可证覆盖。本项目与 Larousse、猫哥法语课程没有隶属或背书关系。
