# ARK-1252 插線動畫

一隻戴工作手套的手，在工廠工作台上把 RJ45 網路線插進 ARK-1252 無風扇工控機的 LAN1 接口。插好後 Link 綠燈亮起、Activity 橘燈閃爍，手隨後離開。

全部用 Python（Blender `bpy` + Cycles 光線追蹤）程序化建模，沒有外部模型或貼圖。

## 執行

```bash
pip install bpy            # Blender 5.x 的 Python 模組，需要 Python 3.13
python scene.py --out frames --frames 1-120 --samples 40           # 渲染全部畫格
python scene.py --out preview --still 62 --samples 16 --res 480x270  # 預覽單張
ffmpeg -framerate 24 -i frames/f_%04d.png -c:v libx264 -pix_fmt yuv420p -crf 18 ark1252.mp4
```

參數：`--res`（預設 960x540）、`--samples`（越高越乾淨、越慢）、`--blend file.blend`（另存場景，可用 Blender 開啟調整）。

## 說明

- ARK-1252 的外觀和接口排列（PWR、DC IN、LAN1/LAN2、USB×2、HDMI、COM）是近似值，因為製作時無法取得官方規格書。要修正的話，改 `scene.py` 裡的接口座標即可。
- 有 GPU 的機器可以把 `sc.cycles.device` 改成 `"GPU"`，並提高解析度和 samples。
