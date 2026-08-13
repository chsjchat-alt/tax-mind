/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // 自定义配色方案
        primary: '#1A56DB',      // 信任蓝
        danger: '#EF4444',       // 柔和红（高风险）
        warning: '#F59E0B',      // 琥珀黄（中风险）
        success: '#10B981',      // 翡翠绿（低风险）
        background: '#F8FAFC',   // 浅灰白
        text: '#1E293B',         // 深灰黑

        // 风险等级颜色映射
        'risk-high': '#EF4444',
        'risk-medium': '#F59E0B',
        'risk-low': '#10B981',
      },
      fontFamily: {
        sans: [
          '"PingFang SC"',
          '"Microsoft YaHei"',
          'system-ui',
          '-apple-system',
          'sans-serif',
        ],
      },
    },
  },
  plugins: [
    require('@tailwindcss/forms'),
  ],
}
