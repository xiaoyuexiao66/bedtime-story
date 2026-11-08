/* 首页交互：录音、保存声音、设置默认声音、说一句话生成故事并自动播放 */

const recordBtn = document.getElementById('recordBtn');
const recordStatus = document.getElementById('recordStatus');
const preview = document.getElementById('preview');
const voiceForm = document.getElementById('voiceForm');
const storyForm = document.getElementById('storyForm');
const storyStatus = document.getElementById('storyStatus');
const topicRecordBtn = document.getElementById('topicRecordBtn');
const topicStatus = document.getElementById('topicStatus');
const defaultVoiceForm = document.getElementById('defaultVoiceForm');
const defaultVoiceStatus = document.getElementById('defaultVoiceStatus');
const autoPanel = document.getElementById('autoPanel');
const autoVoiceLine = document.getElementById('autoVoiceLine');
const storyPlayer = document.getElementById('storyPlayer');
const storyLink = document.getElementById('storyLink');

let recordedBlob = null;
const RECORD_SECONDS = 5;

/* ---------- 录一段声音（给声音克隆用） ---------- */

recordBtn.addEventListener('click', async () => {
  recordBtn.disabled = true;
  recordStatus.textContent = '请在安静的环境下读一句话……';
  try {
    const { blob } = await recordWav(RECORD_SECONDS, (left) => {
      recordStatus.textContent = left > 0 ? `录音中……还剩 ${left} 秒` : '正在处理……';
    });
    recordedBlob = blob;
    preview.src = URL.createObjectURL(blob);
    preview.hidden = false;
    voiceForm.hidden = false;
    recordStatus.textContent = `录好了（${(blob.size / 1024).toFixed(0)} KB），可以试听，然后保存。`;
  } catch (err) {
    recordStatus.textContent = err.message || '录音失败';
  } finally {
    recordBtn.disabled = false;
  }
});

voiceForm.addEventListener('submit', async (e) => {
  e.preventDefault();
  if (!recordedBlob) {
    alert('请先录音');
    return;
  }
  const refText = document.getElementById('refText').value.trim();
  if (!refText) {
    alert('请填写你刚才读的文字，声音克隆需要它');
    return;
  }
  const data = new FormData();
  data.append('name', document.getElementById('voiceName').value.trim() || '妈妈');
  data.append('ref_text', refText);
  data.append('file', recordedBlob, 'voice.wav');

  recordStatus.textContent = '正在保存……';
  try {
    const resp = await fetch('/api/voices', { method: 'POST', body: data });
    const result = await resp.json();
    if (!resp.ok) throw new Error(result.error || '保存失败');
    recordStatus.textContent = '已保存，正在刷新……';
    location.reload();
  } catch (err) {
    recordStatus.textContent = err.message;
  }
});

/* ---------- 默认声音 ---------- */

if (defaultVoiceForm) {
  defaultVoiceForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const voiceId = Number(document.getElementById('defaultVoiceSelect').value);
    if (!voiceId) return;
    defaultVoiceStatus.textContent = '正在保存……';
    try {
      const resp = await fetch('/api/settings/default-voice', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ voice_id: voiceId }),
      });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.error || '保存失败');
      defaultVoiceStatus.textContent = `已保存，默认用【${data.default_voice.name}】`;
      // 把“默认”标记移到刚选的声音上，不用刷新页面
      document.querySelectorAll('.voice-item [data-voice-id]').forEach((item) => {
        const oldTag = item.querySelector('.tag');
        if (oldTag) oldTag.remove();
        if (Number(item.dataset.voiceId) === voiceId) {
          const tag = document.createElement('span');
          tag.className = 'tag';
          tag.textContent = '默认';
          item.appendChild(tag);
        }
      });
    } catch (err) {
      defaultVoiceStatus.textContent = err.message;
    }
  });
}

/* ---------- 说一句话 → 写故事 → 合成 → 播放 ---------- */

const TOPIC_SECONDS = 6;
let autoRunning = false;
let audioUnlocked = false;

// iPhone Safari 只允许在“用户点击”的瞬间启动播放。
// 点麦克风时先播 0.1 秒静音，把播放器解锁；等合成完换真正的音频就能自动播。
function unlockAudio() {
  if (audioUnlocked) return;
  try {
    const silent = encodeWav([new Float32Array(800)], 8000);
    storyPlayer.src = URL.createObjectURL(silent);
    const p = storyPlayer.play();
    if (p && p.catch) p.catch(() => {});
    audioUnlocked = true;
  } catch (_) {
    // 解锁失败不影响流程，最后会提示手动点播放
  }
}

async function transcribe(blob) {
  const data = new FormData();
  data.append('file', blob, 'topic.wav');
  const resp = await fetch('/api/transcribe', { method: 'POST', body: data });
  const result = await resp.json();
  if (!resp.ok) throw new Error(result.error || '没听清');
  const text = (result.text || '').trim();
  if (!text) throw new Error('没听清，再说一次好吗？');
  return text;
}

async function createStory(text, age) {
  const resp = await fetch('/api/stories', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    // utterance 是孩子的原话，后端会让模型顺便判断用哪个声音
    body: JSON.stringify({ topic: text, age, utterance: text }),
  });
  const story = await resp.json();
  if (!resp.ok) throw new Error(story.error || '生成失败');
  return story;
}

async function synthesize(storyId, voiceId) {
  // 合成在后台跑，这里轮询等待完成（见 tts.js）
  return window.waitForTts(storyId, voiceId);
}

topicRecordBtn.addEventListener('click', async () => {
  if (autoRunning) return;
  autoRunning = true;
  topicRecordBtn.disabled = true;
  let timer = null;
  try {
    unlockAudio(); // 必须在点击手势里，录音之前
    autoPanel.hidden = false;
    autoVoiceLine.textContent = '';
    topicStatus.textContent = '我在听……说出你想听的故事吧';

    const { blob } = await recordWav(TOPIC_SECONDS, (left) => {
      topicStatus.textContent = left > 0 ? `我在听……还剩 ${left} 秒` : '让我想想你说的是什么……';
    });

    const text = await transcribe(blob);
    document.getElementById('topic').value = text;
    topicStatus.textContent = `听到了：“${text}”，正在写故事……`;

    const age = Number(document.getElementById('age').value);
    const story = await createStory(text, age);
    storyLink.href = `/story/${story.id}`;
    storyLink.textContent = `查看故事《${story.title}》的文字`;

    if (!story.voice_id) {
      autoVoiceLine.textContent = '还没有录过声音，先在上面录一段，再去故事页点“朗读”。';
      topicStatus.textContent = '故事写好了，但还没有可用的声音。';
      return;
    }

    const voiceName = story.voice_name || '默认声音';
    const started = Date.now();
    autoVoiceLine.textContent = `用【${voiceName}】的声音合成中……`;
    topicStatus.textContent = '故事写好了，正在合成声音……';
    timer = setInterval(() => {
      const seconds = Math.round((Date.now() - started) / 1000);
      autoVoiceLine.textContent = `用【${voiceName}】的声音合成中……已等待 ${seconds} 秒（长故事大约要 1~3 分钟）`;
    }, 1000);

    const data = await synthesize(story.id, story.voice_id);
    clearInterval(timer);
    timer = null;

    storyPlayer.src = data.audio_url + '?t=' + Date.now();
    autoVoiceLine.textContent = `用【${data.voice_name || voiceName}】的声音，合成完成（${data.seconds} 秒）`;
    topicStatus.textContent = '故事开始啦，晚安～';
    const played = storyPlayer.play();
    if (played && played.catch) {
      played.catch(() => {
        autoVoiceLine.textContent += '。浏览器拦住了自动播放，点一下播放器上的 ▶ 就能听';
      });
    }
  } catch (err) {
    topicStatus.textContent = err.message || '没听清，再试一次吧';
    if (!autoVoiceLine.textContent) {
      autoVoiceLine.textContent = '这次没有成功，可以再点一次麦克风。';
    }
  } finally {
    if (timer) clearInterval(timer);
    autoRunning = false;
    topicRecordBtn.disabled = false;
  }
});

/* ---------- 手动输入主题（不自动播放，跳到故事页） ---------- */

storyForm.addEventListener('submit', async (e) => {
  e.preventDefault();
  const topic = document.getElementById('topic').value.trim();
  const age = Number(document.getElementById('age').value);
  if (!topic) return;

  storyStatus.textContent = '正在写故事……大概需要几秒到十几秒';
  const submitBtn = storyForm.querySelector('button[type=submit]');
  submitBtn.disabled = true;
  try {
    const resp = await fetch('/api/stories', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ topic, age }),
    });
    const story = await resp.json();
    if (!resp.ok) throw new Error(story.error || '生成失败');
    location.href = `/story/${story.id}`;
  } catch (err) {
    storyStatus.textContent = err.message;
    submitBtn.disabled = false;
  }
});