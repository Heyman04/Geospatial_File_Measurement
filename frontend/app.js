const apiBaseInput = document.getElementById('apiBase');
const fileInput = document.getElementById('fileInput');
const uploadForm = document.getElementById('uploadForm');
const statusBox = document.getElementById('status');
const fileMetadata = document.getElementById('fileMetadata');
const measurementsContainer = document.getElementById('measurements');

const defaultApiBase = 'http://localhost:8080';

function setStatus(message, isError = false) {
  statusBox.textContent = message;
  statusBox.style.borderLeftColor = isError ? '#dc2626' : '#2563eb';
  statusBox.style.background = isError ? '#fef2f2' : '#eaf2ff';
}

function renderMetadata(data) {
  fileMetadata.textContent = JSON.stringify(data, null, 2);
}

function renderMeasurements(items) {
  if (!items || !items.length) {
    measurementsContainer.textContent = 'No measurements available.';
    measurementsContainer.className = 'measurements-empty';
    return;
  }

  measurementsContainer.className = '';
  measurementsContainer.innerHTML = items
    .map(
      (item) => `
        <div class="measurement-card">
          <strong>Feature ${item.feature_index}</strong><br>
          Type: ${item.geometry_type}<br>
          CRS: ${item.crs}<br>
          Properties: <pre style="margin: 0.5rem 0; font-size: 0.85em; background: #f3f4f6; padding: 0.5rem; border-radius: 4px; overflow-x: auto;">${JSON.stringify(item.properties, null, 2)}</pre>
          Geometry: <pre style="margin: 0.5rem 0 1rem 0; font-size: 0.85em; background: #f3f4f6; padding: 0.5rem; border-radius: 4px; overflow-x: auto;">${JSON.stringify(item.geometry, null, 2)}</pre>
          Area: ${item.area ?? 'N/A'}<br>
          Length: ${item.length ?? 'N/A'}<br>
          Unsupported: ${item.unsupported_reason ?? 'None'}
        </div>
      `,
    )
    .join('');
}

uploadForm.addEventListener('submit', async (event) => {
  event.preventDefault();

  const apiBase = apiBaseInput.value.trim() || defaultApiBase;
  const file = fileInput.files[0];

  if (!file) {
    setStatus('Please choose a geospatial file first.', true);
    return;
  }

  const formData = new FormData();
  formData.append('file', file);

  try {
    setStatus('Uploading file...');
    const uploadResponse = await fetch(`${apiBase}/api/files/`, {
      method: 'POST',
      body: formData,
    });

    const uploadData = await uploadResponse.json();

    if (!uploadResponse.ok) {
      throw new Error(uploadData.detail || 'Upload failed.');
    }

    renderMetadata(uploadData);

    const measurementsResponse = await fetch(`${apiBase}/api/files/${uploadData.id}/measurements/`);
    const measurementsData = await measurementsResponse.json();

    if (!measurementsResponse.ok) {
      throw new Error(measurementsData.detail || 'Measurement fetch failed.');
    }

    renderMeasurements(measurementsData);
    setStatus(`Processed ${uploadData.filename} successfully.`);
  } catch (error) {
    console.error(error);
    setStatus(error.message || 'Something went wrong.', true);
    fileMetadata.textContent = 'No valid file response received.';
    measurementsContainer.textContent = 'No measurements available.';
  }
});
