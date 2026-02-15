/** @type {import('tailwindcss').Config} */
module.exports = {
    content: [
        "./index.html",
        "./src/**/*.{js,ts,jsx,tsx}",
    ],
    theme: {
        extend: {
            colors: {
                primary: "#6366f1", // indigo-500
                secondary: "#8b5cf6", // violet-500
                dark: "#0f172a", // slate-900
                light: "#f8fafc", // slate-50
            },
        },
    },
    plugins: [],
}
