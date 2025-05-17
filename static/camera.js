const video = document.getElementById('video');
const canvas = document.getElementById('canvas');
const takePhotoButton = document.getElementById('take-photo');


if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
    navigator.mediaDevices.getUserMedia({ video: true })
        .then(stream => {
        const video = document.getElementById('video');
        video.srcObject = stream;
    })
    .catch(error => {
        console.error('Error accessing camera:', error);
    });
} else {
    console.log("getUserMedia is not supported in this browser. Please upload an image instead.")
}

takePhotoButton.addEventListener('click', () => {
  canvas.width = video.videoWidth;
  canvas.height = video.videoHeight;
  const ctx = canvas.getContext('2d');
  ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
  const imageDataURL = canvas.toDataURL('image/png');
  const link = document.createElement('a');
  link.href = imageDataURL;
  link.download = 'photo.png';
  link.click();
});
