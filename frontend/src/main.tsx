import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { ConfigProvider } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import App from './App'
import './index.css'

// Ant Design 中文主题配置
const antdTheme = {
  token: {
    colorPrimary: '#1A56DB',
    borderRadius: 8,
    fontFamily: '"PingFang SC", "Microsoft YaHei", system-ui, -apple-system, sans-serif',
  },
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <BrowserRouter>
      <ConfigProvider locale={zhCN} theme={antdTheme}>
        <App />
      </ConfigProvider>
    </BrowserRouter>
  </React.StrictMode>,
)
