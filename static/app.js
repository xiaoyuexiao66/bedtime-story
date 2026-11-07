/* 首页交互：录音、保存声音、生成故事 */

const recordBtn = document.getElementById('recordBtn');
const recordStatus = document.getElementById('recordStatus');
const preview = document.getElementById('preview');
const voiceForm = document.getElementById('voiceForm');
const storyForm = document.getElementById('storyForm');
const storyStatus = document.getElementById('storyStatus');
const topicRecordBtn = document.getElementById('topicRecordBtn');
const topicStatus = document.getElementById('topicStatus');

let recordedBlob = null;
const RECORD_SECONDS = 5;

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

/* 按住/点一下说一句话，识别后自动填主题并生成故事 */
const TOPIC_SECONDS = 6;

topicRecordBtn.addEventListener('click', async () => {
  topicRecordBtn.disabled = true;
  topicStatus.textContent = '我在听……说出你想听的故事吧';
  try {
    const { blob } = await recordWav(TOPIC_SECONDS, (left) => {
      topicStatus.textContent = left > 0 ? `我在听……还剩 ${left} 秒` : '让我想想你说的是什么……';
    });
    const data = new FormData();
    data.append('file', blob, 'topic.wav');
    const resp = await fetch('/api/transcribe', { method: 'POST', body: data });
    const result = await resp.json();
    if (!resp.ok) throw new Error(result.error || '没听清');
    const text = (result.text || '').trim();
    if (!text) throw new Error('没听清，再说一次好吗？');

    document.getElementById('topic').value = text;
    topicStatus.textContent = `听到了：“${text}”，正在生成故事……`;
    topicRecordBtn.disabled = false;
    // Safari 15 没有 requestSubmit，用事件兜底
    if (storyForm.requestSubmit) storyForm.requestSubmit();
    else storyForm.dispatchEvent(new Event('submit', { cancelable: true, bubbles: true }));
  } catch (err) {
    topicStatus.textContent = err.message || '没听清，再试一次吧';
    topicRecordBtn.disabled = false;
  }
});

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