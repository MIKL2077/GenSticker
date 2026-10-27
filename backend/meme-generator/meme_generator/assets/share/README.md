# Share covers

`cover-v2.jpg` is a 600×480 (5:4) GenSticker share cover, generated on 2026-10-26 from the project's existing `frontend/src/static/logo.png` brand reference using the imagegen skill. The blue/yellow mask characters become three reaction stickers, with brand text and large Chinese captions legible at chat-card size.

The source generation is retained in the private workspace artifacts. This optimized JPEG is the shipped asset; it is served by `/share/cover-v2.jpg` with public immutable caching and does not contain user photos. Introduce a new filename/route when replacing it. No runtime model call or client canvas is required.

On 2026-10-27, three additional 600×480 JPEGs were generated using built-in imagegen with the existing logo and cover as references:

- [cover-v3.jpg](cover-v3.jpg): coffee / confidence / laughter — “先喝一口”“问题不大”“快乐加倍”.
- [cover-v4.jpg](cover-v4.jpg): playful sticker battle — “接招吧！”“你开心就好”.
- [cover-v5.jpg](cover-v5.jpg): surprise / affection / confidence — “好家伙”“被可爱到了”“稳稳拿捏”.

The exact [prompt set](PROMPTS.md) is retained for later variations. All four assets are served from an explicit allowlist at `/share/{name}`. The frontend selects randomly on each mini-program share callback, excluding the previously chosen cover in the current app session. Sharing an explicitly generated image continues to use that image and does not consume a cover choice. These server assets add no media bytes to the mini-program package; the legacy v2 URL stays valid.
