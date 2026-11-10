"""SDR Web Monitor: FastAPI + WebSocket для віддаленого керування SDR
та потокової візуалізації спектра."""
import asyncio
import json
import random

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

app = FastAPI(title="SDR Web Monitor")

# Глобальний стан SDR
sdr_state = {
    "current_frequency": 100.5,  # MHz
    "is_running": True,
}


class FrequencyCommand(BaseModel):
    # діапазон типового RTL-SDR: 24 - 1766 MHz
    frequency_mhz: float = Field(..., ge=24.0, le=1766.0)


def set_hardware_freq(freq_mhz: float) -> None:
    """Заглушка драйвера SDR.
    Для реального RTL-SDR (pyrtlsdr): sdr.center_freq = freq_mhz * 1e6
    """
    pass


HTML_PAGE = """
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>SDR Monitor</title>
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <style>
    body { font-family: sans-serif; background-color: #121212; color: #fff;
           margin: 0; padding: 10px; text-align: center; }
    canvas { background-color: #000; width: 100%; max-width: 600px; height: 250px;
             border: 1px solid #333; border-radius: 8px; }
    .control-panel { margin-top: 20px; padding: 15px; background: #1e1e1e;
                     border-radius: 8px; display: inline-block; width: 100%;
                     max-width: 570px; box-sizing: border-box; }
    input[type="number"] { padding: 10px; font-size: 18px; width: 120px;
                           border-radius: 5px; border: none; }
    button { padding: 10px 20px; font-size: 18px; background-color: #0d6efd;
             color: white; border: none; border-radius: 5px; cursor: pointer; }
    button:active { background-color: #0b5ed7; }
    #status { margin-top: 10px; color: #0dcaf0; font-size: 14px; }
  </style>
</head>
<body>
  <h2>SDR Spectrum Monitor</h2>
  <canvas id="spectrumCanvas" width="600" height="250"></canvas>

  <div class="control-panel">
    <label>Частота (MHz): </label>
    <input type="number" id="freqInput" step="0.1" value="100.5">
    <button onclick="setFrequency()">ВСТАНОВИТИ</button>
    <div id="status">Підключення до SDR...</div>
  </div>

  <script>
    const canvas = document.getElementById('spectrumCanvas');
    const ctx = canvas.getContext('2d');
    const statusEl = document.getElementById('status');

    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    const ws = new WebSocket(`${proto}://${location.host}/ws/spectrum`);

    ws.onerror = function () {
      statusEl.innerText = "Помилка WebSocket: " + ws.url;
      statusEl.style.color = "#ffc107";
    };
    ws.onmessage = function (event) {
      const data = JSON.parse(event.data);
      drawSpectrum(data.fft_data);
      statusEl.style.color = "#0dcaf0";
      statusEl.innerText = `Активна частота: ${data.frequency} MHz | Оновлення: Live`;
    };
    ws.onclose = function () {
      statusEl.innerText = "Зв'язок з SDR втрачено!";
      statusEl.style.color = "#dc3545";
    };

    function drawSpectrum(fftArray) {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.beginPath();
      ctx.strokeStyle = '#00ff00';
      ctx.lineWidth = 2;
      const step = canvas.width / (fftArray.length - 1);
      for (let i = 0; i < fftArray.length; i++) {
        const x = i * step;
        const y = canvas.height - (fftArray[i] / 100 * canvas.height);
        if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
      }
      ctx.stroke();
    }

    async function setFrequency() {
      const newFreq = parseFloat(document.getElementById('freqInput').value);
      const res = await fetch('/api/frequency', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ frequency_mhz: newFreq })
      });
      if (res.ok) {
        console.log("Частоту змінено");
      } else {
        statusEl.style.color = "#ffc107";
        statusEl.innerText = "Некоректна частота (24 - 1766 MHz)";
      }
    }
  </script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
async def get_ui():
    """Віддає веб-інтерфейс моніторингу."""
    return HTML_PAGE


@app.post("/api/frequency")
async def change_frequency(cmd: FrequencyCommand):
    """Приймає команду зі смартфона та змінює частоту SDR."""
    sdr_state["current_frequency"] = cmd.frequency_mhz
    set_hardware_freq(cmd.frequency_mhz)
    print(f"[SDR CONTROL] Частота перелаштована на {cmd.frequency_mhz} MHz", flush=True)
    return {"status": "ok", "new_frequency": cmd.frequency_mhz}


@app.websocket("/ws/spectrum")
async def spectrum_stream(websocket: WebSocket):
    """Нескінченно стримить дані спектра на підключений клієнт."""
    await websocket.accept()
    print("[МЕРЕЖА] Клієнт підключився до потоку спектра", flush=True)
    try:
        while True:
            # ІМІТАЦІЯ: тут має бути читання реального FFT-буфера з SDR
            mock_fft = [random.randint(10, 40) for _ in range(64)]
            mock_fft[31] = random.randint(80, 100)
            mock_fft[32] = random.randint(70, 90)

            payload = {
                "frequency": sdr_state["current_frequency"],
                "fft_data": mock_fft,
            }
            await websocket.send_text(json.dumps(payload))
            await asyncio.sleep(0.05)  # ~20 кадрів/с
    except WebSocketDisconnect:
        print("[МЕРЕЖА] Клієнт відключився від потоку", flush=True)


if __name__ == "__main__":
    print("Запуск SDR Web Server на порту 8000...")
    uvicorn.run(app, host="0.0.0.0", port=8000)
