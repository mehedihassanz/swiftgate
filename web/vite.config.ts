import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/v1": "http://localhost:8000",
      "/admin": "http://localhost:8000",
      "/auth": "http://localhost:8000",
      "/user": "http://localhost:8000",
      "/health": "http://localhost:8000",
    },
  },
});
