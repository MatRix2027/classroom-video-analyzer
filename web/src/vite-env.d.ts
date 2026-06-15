/// <reference types="vite/client" />

declare module '*.css' {
  const content: string;
  export default content;
}

declare module 'video.js/dist/video-js.css' {
  const content: string;
  export default content;
}
