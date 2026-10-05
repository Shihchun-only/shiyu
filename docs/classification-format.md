# 分类课件约定 v1

供后续制作课件时使用。软件只导入分类数据，自行获取词典；不要把预填 Larousse 资料作为导入前提。

JSON 顶层：`format: "shiyu.annotated-course"`、`schemaVersion: 1`、`stage: "classification-only"`、`pages`。

每页包括 `id,name,width,height,image,regions,words`。image 为 PNG/JPEG/WebP 的 base64 data URL。regions 每项包括唯一 id、text、kind、lang、box。box 为 `[左,上,宽,高]`，均为相对原始图片的 0–1 坐标。

法语单词用 `kind: "word", lang: "fr"`，只有这些区域建立词典任务。英语 en、中文 zh、音标 und-fonipa、字母组合 grapheme；图片装饰及界面控制另标 nontext/ui。不要把 ai、eu、on 等发音教学中的字母组合当作词语查询。

words 与法语区域通过相同 id 对应，可含 sentence（准确的课内短语/上下文）、sourceGloss（课件原文的中文解释）、reviewNote。短语中文必须注明对应整个短语，不能误当某个组成词的单独含义。遇到遮挡或疑似错字，保留核对提示，不声称确定。

可选 pattern: `{text,ipa}`；originalRule 为本页课件规则原文。保留作者标识及原图，不悄悄改写教学内容。

分类 PDF 每页使用原图，并添加不可见文字层。将完整 JSON 附件命名为 `shiyu-course.json`；也支持 `/ShiyuCourseB64` 元数据保存 UTF-8 JSON 的 URL-safe base64（可省略末尾等号）。导入器优先读取该元数据，否则读取附件。

示例课件目录中有可直接参考的 JSON 和 PDF。包含私有标注的分类 PDF 需要本软件读取；普通 PDF 阅读器不会自动显示这些分类，也不会自动播放词典音频。
