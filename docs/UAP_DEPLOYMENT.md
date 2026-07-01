# UAP Deployment Notes

## Current Site

- URL: https://classroom-video-analyzer.cd.huohuasiwei.cn/
- Health check: `/api/health`
- Model diagnostics: `/api/config/models`
- Runtime data directory: `/data`

## Required Runtime Secrets

The deployed container does not include `config/api_keys.json`. This is intentional: API keys must not be committed to git or bundled into the deployment zip.

Configure the following environment variable in the UAP site runtime:

- `API_KEYS_JSON`: the full JSON content of the local `config/api_keys.json`

The app reads keys in this order:

1. `API_KEYS_JSON` environment variable
2. `/app/config/api_keys.json` inside the container

For UAP, use option 1.

## Expected Model Diagnostics

Before `API_KEYS_JSON` is configured:

```json
{
  "text_model": "unknown",
  "text_enabled": false,
  "vision_model": "unknown",
  "vision_enabled": false,
  "config_status": "missing_or_invalid"
}
```

After `API_KEYS_JSON` is configured correctly:

```json
{
  "text_provider": "deepseek",
  "text_model": "deepseek-chat",
  "text_enabled": true,
  "vision_provider": "doubao_vision",
  "vision_model": "doubao-vision-pro-32k",
  "vision_enabled": true,
  "config_status": "ok"
}
```

## Safe Deployment Flow

Use a clean git archive instead of uploading the working directory. This avoids sending `.venv`, local data, uploaded videos, and local secret files.

```powershell
$zip = "D:\Spark\work_x\classroom-video-analyzer-uap.zip"
if (Test-Path $zip) { Remove-Item -LiteralPath $zip -Force }
git archive --format=zip --output=$zip HEAD
npx.cmd --yes https://adp.bg.huohua.cn/uap.tgz site deploy $zip --name classroom-video-analyzer -o json
```

Then verify:

```powershell
curl.exe -sS https://classroom-video-analyzer.cd.huohuasiwei.cn/api/health
curl.exe -sS https://classroom-video-analyzer.cd.huohuasiwei.cn/api/config/models
```

## Notes

- Do not paste API keys into chat.
- Do not commit `config/api_keys.json`.
- If UAP git deploy fails due to GitHub connectivity, use the zip flow above.
- If Docker build stalls while installing `ffmpeg`, keep the domestic apt mirror in `Dockerfile`.
