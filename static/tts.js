/* 合成是后台任务：先发起，再轮询进度。
   这样不用把 2 分钟的合成塞进一个请求，避免手机浏览器超时。 */

window.startTts = async function (storyId, voiceId) {
  const resp = await fetch(`/api/stories/${storyId}/tts`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(voiceId ? { voice_id: Number(voiceId) } : {}),
  });
  const data = await resp.json();
  if (!resp.ok) throw new Error(data.error || '合成失败');
  return data;
};

window.waitForTts = async function (storyId, voiceId, onTick) {
  await window.startTts(storyId, voiceId);
  const deadline = Date.now() + 10 * 60 * 1000; // 最多等 10 分钟
  while (Date.now() < deadline) {
    await new Promise((resolve) => setTimeout(resolve, 1500));
    const resp = await fetch(`/api/stories/${storyId}/tts/status`);
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.error || '查询合成进度失败');
    if (data.state === 'done') return data;
    if (data.state === 'error') throw new Error(data.error || '合成失败');
    if (data.state === 'idle') {
      throw new Error('合成任务断掉了，请重新点一次朗读');
    }
    if (onTick) onTick(data);
  }
  throw new Error('合成等太久了（超过 10 分钟），请到故事页重试');
};