/* 首页交互：录音、保存声音、生成故事 */

const recordBtn = document.getElementById('recordBtn');
const recordStatus = document.getElementById('recordStatus');
const preview = document.getElementById('preview');
const voiceForm = document.getElementById('voiceForm');
const storyForm = document.getElementById('storyForm');
const storyStatus = document.getElementById('storyStatus');

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