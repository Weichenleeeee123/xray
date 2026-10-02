# 小企报告助手动画

- 生成方式：内置 imagegen，参考 `research-room/public/xiaoqi.png` 和 `xiaoqi-action-cycles.png`。
- 最终素材：`research-room/public/xiaoqi-assistant-sprites.png`，PNG，1774 × 887，1,430,327 bytes。
- SHA-256：`D4E9274DAD4A6310366F060532A37C295D1ADE861CA7D28395E636B73FC35C55`。
- 素材为 4 列 × 2 行，首行闲置（眨眼、招手），次行思考（翻资料）。背景是暖白 RGB，非透明 alpha。已移除亮度与 multiply 的底色近似方案；`web/xiaoqi-silhouettes.css` 对八帧分别做角色轮廓裁切，图像原文件不改写，角色外部显示页面原有底色。
- 按用户最终意见：小企站在“想问某一条”提示上方的整条分隔线上，脚底逐帧对齐；角色位于提示文字和输入框上方，无头像边框、卡片背景；窄屏入口也无胶囊框。
- `output/playwright/trace-qi-outline.py` 只读原图生成 CSS 轮廓及每帧脚底偏移。第三次 imagegen 去背景仍返回 RGB 棋盘图，未采用该输出。
- `S.busyCaseId` 将思考动作绑定到请求所属案卷；成功、失败都恢复闲置。减少动态效果设置停用动画。
- 验证：27 项前端回归通过；Playwright 模拟成功/失败响应验证动画切换、失败恢复输入、窄屏开关及减少动态效果；不调用付费模型、不写入案卷。
- 图片恢复脚本两次扫描超时；改用本次 imagegen 工具明确返回的生成路径复制，并通过 Pillow 校验可读性与 SHA-256 校验文件。没有使用旧结果，也未删除文件。

## 生成提示词

```text
Use case: stylized-concept
Asset type: production animation sprite sheet for the existing Xiaoqi enterprise research AI assistant.
Input images: image 1 character identity reference, image 2 EXACT existing illustrated rendering style and navy business suit reference. Preserve Xiaoqi's identity: ivory white goose, orange beak, navy eyes, mint green segmented ring around the visible eye, little swept feather crest, navy business suit and white collar.
Primary request: Generate a single transparent PNG sprite sheet, 2048 x 1024, exact grid of 4 columns and 2 rows, eight square 512x512 cells. No background, genuine transparent alpha. All eight cells depict the SAME friendly suited goose, full body in a front three-quarter view facing slightly left, feet on identical baseline, same size and same fixed central registration. Each figure occupies central 75% width and 82% height, enough padding to avoid touching other cells. Small enough details to remain legible as an 80px assistant button. Follow the hand-painted cartoon linework and warm cream shading of image 2, not pixel art and not glossy 3D.
Top row is idle greeting loop: frame 1 neutral friendly smile with wings resting, frame 2 eyes closed in a blink with slight head tilt, frame 3 raises one wing in a gentle hello, frame 4 lowers that wing halfway toward the frame 1 pose. Feet never change position.
Bottom row is thoughtful research loop: every frame holds the same small open brown dossier at belly height; frame 1 looking down at pages, frame 2 head gently tilted considering a detail, frame 3 one wing turning a page, frame 4 looking thoughtfully at the book again. Body registration unchanged. Calm diligent expression, no worry.
Constraints: exactly eight separate poses, strict evenly spaced 4x2 grid; NO labels, NO text, NO grid lines, NO circles or button backgrounds, NO sparkles, no detached accessories. Preserve character identity, suit, illustration style and scale across all frames. Transparent canvas all around each figure.
```

## 背景修正提示词

```text
Use case: precise-object-edit. Edit the supplied 4 by 2 animation sprite sheet. Change ONLY the background: remove all the grey checkerboard texture, replacing it with perfectly uniform solid warm white #faf8f3 (RGB 250,248,243), no texture, no gradient, no shadow. Keep exactly the eight goose characters, their poses, navy suits, green eye rings, cartoon illustration, outlines, absolute positions, consistent sizes, and the exact same 4 columns x 2 rows layout unchanged. This is a website sprite sheet on a warm paper button, its background MUST be a flat solid warm white, no checkerboard anywhere. Do not add labels or grid lines. Preserve 2:1 canvas aspect ratio.
```
