document.getElementById('grant').addEventListener('click', async () => {
  const result = document.getElementById('result');
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    stream.getTracks().forEach((track) => track.stop());
    result.textContent = 'Access granted. Close this tab, go back to your Meet tab and press Start again.';
  } catch (error) {
    result.textContent = 'Access was not granted: ' + error.message + '. Allow the microphone for this extension in Chrome site settings.';
  }
});
