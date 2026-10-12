import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  server: {
    // Send API calls to the FastAPI server during development.
    proxy: { "/api": "http://localhost:8000" },
  },
  test: {
    environment: "node",
  },
});
