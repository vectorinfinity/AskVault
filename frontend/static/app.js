const form = document.querySelector('#question-form');
const question = document.querySelector('#question');
const button = document.querySelector('#ask-button');
const buttonLabel = document.querySelector('#button-label');
const result = document.querySelector('#result');
const answer = document.querySelector('#answer');
const sources = document.querySelector('#sources');
const sourcesContainer = document.querySelector('#sources-container');
const copyButton = document.querySelector('#copy-button');
const pdfFile = document.querySelector('#pdf-file');
const uploadButton = document.querySelector('#upload-button');
const processButton = document.querySelector('#process-button');
const uploadStatus = document.querySelector('#upload-status');
let busy = false;
let uploadedFilename = null;
let statusPoller = null;

function setUploadStatus(message, type = '') {
  uploadStatus.className = `tool-status ${type}`;
  uploadStatus.textContent = message;
}

function stopStatusPolling() {
  if (statusPoller) window.clearInterval(statusPoller);
  statusPoller = null;
}

async function refreshProcessStatus() {
  try {
    const response = await fetch('/process-status');
    const data = await response.json();
    if (!data.success || data.filename !== uploadedFilename) return;
    setUploadStatus(data.message, data.state === 'failed' ? 'error' : data.state === 'completed' ? 'ready' : '');
    if (data.state === 'processing') return;
    processButton.disabled = data.state === 'completed';
    uploadButton.disabled = !pdfFile.files.length;
    stopStatusPolling();
  } catch {
    setUploadStatus('Unable to check processing status.', 'error');
    stopStatusPolling();
  }
}

pdfFile.addEventListener('change', () => {
  uploadedFilename = null;
  stopStatusPolling();
  processButton.disabled = true;
  const file = pdfFile.files[0];
  uploadButton.disabled = !file;
  setUploadStatus(file ? `Selected: ${file.name}` : 'Choose a PDF to add it to your document collection.');
});

uploadButton.addEventListener('click', async () => {
  const file = pdfFile.files[0];
  if (!file) return;
  if (!file.name.toLowerCase().endsWith('.pdf')) {
    setUploadStatus('Please choose a PDF file.', 'error');
    return;
  }
  uploadButton.disabled = true;
  setUploadStatus('Uploading PDF…');
  try {
    const formData = new FormData();
    formData.append('file', file);
    const response = await fetch('/upload-pdf', {method: 'POST', body: formData});
    const data = await response.json();
    if (!response.ok || !data.success) throw new Error(data.error || 'Could not upload PDF.');
    uploadedFilename = data.filename;
    processButton.disabled = false;
    setUploadStatus(data.message, 'ready');
  } catch (error) {
    setUploadStatus(error.message, 'error');
    uploadButton.disabled = false;
  }
});

processButton.addEventListener('click', async () => {
  if (!uploadedFilename) return;
  processButton.disabled = true;
  setUploadStatus('Starting PDF processing…');
  try {
    const response = await fetch('/process-pdf', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({filename: uploadedFilename})
    });
    const data = await response.json();
    if (!response.ok || !data.success) throw new Error(data.error || 'Could not start PDF processing.');
    setUploadStatus(data.message);
    stopStatusPolling();
    statusPoller = window.setInterval(refreshProcessStatus, 2500);
    refreshProcessStatus();
  } catch (error) {
    setUploadStatus(error.message, 'error');
    processButton.disabled = false;
  }
});

async function checkHealth() {
  const connection = document.querySelector('#connection');
  try {
    const response = await fetch('/health', {signal: AbortSignal.timeout(5000)});
    if (!response.ok) throw new Error();
    connection.className = 'connection online';
    connection.replaceChildren(Object.assign(document.createElement('span'), {className: 'dot'}), 'API connected');
  } catch {
    connection.className = 'connection offline';
    connection.replaceChildren(Object.assign(document.createElement('span'), {className: 'dot'}), 'API unavailable');
  }
}
checkHealth();
setInterval(checkHealth, 30000);

document.querySelectorAll('.suggestions button').forEach(suggestion => {
  suggestion.addEventListener('click', () => {
    if (busy) return;
    question.value = suggestion.textContent;
    question.focus();
  });
});
question.addEventListener('keydown', event => {
  if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') {
    event.preventDefault();
    form.requestSubmit();
  }
});
form.addEventListener('submit', async event => {
  event.preventDefault();
  const value = question.value.trim();
  if (busy || !value) return;
  busy = true;
  button.disabled = true;
  buttonLabel.textContent = 'Finding answer…';
  result.hidden = false;
  result.setAttribute('aria-busy', 'true');
  document.querySelector('#result-title').textContent = 'Answer';
  document.querySelector('#asked-question').textContent = value;
  document.querySelector('#result-meta').textContent = '';
  answer.className = 'loading';
  answer.textContent = 'Searching your documents and preparing an answer…';
  sources.replaceChildren();
  sourcesContainer.hidden = true;
  copyButton.hidden = true;
  try {
    const response = await fetch('/ask', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({question: value, top_k: Number(document.querySelector('#top-k').value)}),
      signal: AbortSignal.timeout(240000)
    });
    const data = await response.json();
    if (!response.ok || !data.success) throw new Error(data.error || 'Unable to answer. Please try again.');
    answer.className = '';
    answer.textContent = data.answer;
    copyButton.hidden = false;
    copyButton.textContent = 'Copy answer';
    for (const source of data.sources || []) {
      const item = document.createElement('li');
      item.textContent = source.filename;
      const section = document.createElement('span');
      section.textContent = source.section || 'Document reference';
      item.append(section);
      sources.append(item);
    }
    sourcesContainer.hidden = !sources.childElementCount;
    document.querySelector('#result-meta').textContent = [data.model, Number.isInteger(data.chunk_count) ? `${data.chunk_count} passages used` : '', data.truncated ? 'Source context shortened to fit the model' : ''].filter(Boolean).join(' · ');
  } catch (error) {
    document.querySelector('#result-title').textContent = 'Unable to get an answer';
    answer.className = 'error';
    answer.textContent = error.name === 'TimeoutError' ? 'The request took too long. Please try a more specific question.' : error instanceof TypeError ? 'Cannot reach the server. Check that the project is running and try again.' : error.message;
  } finally {
    busy = false;
    button.disabled = false;
    buttonLabel.textContent = 'Ask question';
    result.setAttribute('aria-busy', 'false');
  }
});
copyButton.addEventListener('click', async () => {
  try {
    await navigator.clipboard.writeText(answer.textContent);
    copyButton.textContent = 'Copied';
  } catch {
    copyButton.textContent = 'Select the answer to copy';
  }
});
