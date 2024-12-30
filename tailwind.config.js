/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./validator/templates/**/*.html",
    "./validator/static/src/**/*.js"
  ],
  theme: {
    extend: {},
  },
  plugins: [
    require('@tailwindcss/forms')
  ],
}

