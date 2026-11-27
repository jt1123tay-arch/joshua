# ARK-1252 插線動畫

一隻戴白色針織 PU 浸膠手套的右手，在工廠工作台上把 RJ45 網路線插進 ARK-1252 無風扇工控機的 LAN1 接口。插好後 Link 綠燈亮起、Activity 橘燈閃爍，手隨後離開。

全部用 Python（Blender `bpy` + Cycles 光線追蹤）程序化建模，沒有外部模型或貼圖。

## 執行

```bash
pip install bpy            # Blender 5.x 的 Python 模組，需要 Python 3.13
python scene.py --out frames --frames 1-120 --samples 40           # 渲染全部畫格
python scene.py --out preview --still 62 --samples 16 --res 480x270  # 預覽單張
ffmpeg -framerate 24 -i frames/f_%04d.png -c:v libx264 -pix_fmt yuv420p -crf 18 ark1252.mp4
```

參數：`--res`（預設 960x540，正式版用 1920x1080）、`--samples`（越高越乾淨、越慢）、`--blend file.blend`（另存場景，可用 Blender 開啟調整）、`--step N`（每 N 格渲染一張，快速檢查動作）、`--cam x,y,z,tx,ty,tz[,lens]`（固定除錯鏡頭）、`--check`（逐格檢查網路線與手、手與機身是否穿模，印出距離後結束）。

## 說明

- ARK-1252 的外觀照 `reference/ark1252_front.png` 建模：直立機身、兩側直向散熱鰭片、右側銀色飾條（ADVANTECH／ARK-1252 直排字）。正面接口由上到下是：電源鍵、DIO（DB9）、音源孔×2、3 組「LAN＋USB×2」、USB 7＋Type-C、DP＋HDMI。
- 正面接口位置在 `scene.py` 的 `OPEN` 清單，用「距左緣 u mm、距上緣 v mm」表示。機身尺寸（72×130×200 mm）是從照片比例估算的，有規格書可再修正 `BW`、`BD`、`BH`。
- 有 GPU 的機器可以把 `sc.cycles.device` 改成 `"GPU"`，並提高解析度和 samples。
- 手是用手指骨架（每指三節、可設定彎曲角度）加手掌、大魚際等圓柱／橢球體組合，再以體素重建（voxel remesh）融合成一個網格，加上布料皺褶位移。手套材質：手背白色針織、掌面與指尖灰色 PU 塗層（依每個頂點朝向自動判斷）。放開插頭的動作是 shape key（拇指上抬、食指張開）。
- 握法：拇指壓在插頭護套上方，護套靠在食指中節側面，其餘三指自然彎曲；手臂從右前方伸入，袖子為深藍工作服加羅紋袖口。調整姿勢改 `FING`（各指彎曲角度）和 `PSI, PHI, RHO`（手的偏航、俯仰、翻轉角）。
