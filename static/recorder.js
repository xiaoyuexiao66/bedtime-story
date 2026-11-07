/* 浏览器录音并编码成 WAV。
   ZipVoice 需要 wav 作为参考音频，所以这里不用 webm/ogg，
   而是直接把麦克风采样编码成 16-bit PCM WAV，避免依赖 ffmpeg。 */

function encodeWav(chunks, sampleRate) {
  let length = 0;
  for (const c of chunks) length += c.length;

  const buffer = new ArrayBuffer(44 + length * 2);
  const view = new DataView(buffer);
  const writeStr = (offset, str) => {
    for (let i = 0; i < str.length; i++) view.setUint8(offset + i, str.charCodeAt(i));
  };

  writeStr(0, 'RIFF');
  view.setUint32(4, 36 + length * 2, true);
  writeStr(8, 'WAVE');
  writeStr(12, 'fmt ');
  view.setUint32(16, 16, true);          // fmt chunk 大小
  view.setUint16(20, 1, true);           // PCM
  view.setUint16(22, 1, true);           // 单声道
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true);
  view.setUint16(32, 2, true);           // block align
  view.setUint16(34, 16, true);          // 16 bit
  writeStr(36, 'data');
  view.setUint32(40, length * 2, true);

  let offset = 44;
  for (const chunk of chunks) {
    for (let i = 0; i < chunk.length; i++) {
      const s = Math.max(-1, Math.min(1, chunk[i]));
      view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7fff, true);
      offset += 2;
    }
  }
  return new Blob([view], { type: 'audio/wav' });
}

async function recordWav(seconds, onTick) {
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    throw new Error('当前浏览器不支持录音。iPhone 请用 Safari 打开，并确认地址是 https://');
  }

  const stream = await navigator.mediaDevices.getUserMedia({
    audio: {
      channelCount: 1,
      echoCancellation: true,
      noiseSuppression: true,
      autoGainControl: true,
    },
  });

  const AudioCtx = window.AudioContext || window.webkitAudioContext;
  const ctx = new AudioCtx();
  const source = ctx.createMediaStreamSource(stream);
  const processor = ctx.createScriptProcessor(4096, 1, 1);
  const chunks = [];

  processor.onaudioprocess = (e) => {
    chunks.push(new Float32Array(e.inputBuffer.getChannelData(0)));
  };
  source.connect(processor);
  processor.connect(ctx.destination);

  const sampleRate = ctx.sampleRate;

  await new Promise((resolve) => {
    let left = seconds;
    if (onTick) onTick(left);
    const timer = setInterval(() => {
      left -= 1;
      if (onTick) onTick(left);
      if (left <= 0) {
        clearInterval(timer);
        resolve();
      }
    }, 1000);
  });

  processor.disconnect();
  source.disconnect();
  stream.getTracks().forEach((t) => t.stop());
  await ctx.close();

  return { blob: encodeWav(chunks, sampleRate), sampleRate };
}

window.recordWav = recordWav;