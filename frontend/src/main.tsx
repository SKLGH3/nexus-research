import "@ant-design/v5-patch-for-react-19";
import "antd/dist/reset.css";
import { App as AntApp, ConfigProvider, theme } from "antd";
import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./styles.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ConfigProvider
      theme={{
        algorithm: theme.defaultAlgorithm,
        token: {
          colorPrimary: "#ef6a4c",
          colorSuccess: "#2f7d62",
          colorWarning: "#b77a2c",
          colorError: "#bd4a4a",
          colorInfo: "#355f8a",
          colorBgBase: "#f4f0e8",
          colorBgContainer: "#fffdf9",
          colorText: "#18202b",
          colorTextSecondary: "#68717d",
          colorBorder: "#d8d2c7",
          borderRadius: 4,
          fontFamily: "'IBM Plex Sans', 'PingFang SC', 'Microsoft YaHei', system-ui, sans-serif",
          fontFamilyCode: "'JetBrains Mono', Consolas, monospace"
        },
        components: {
          Button: { controlHeightLG: 44, primaryShadow: "none" },
          Input: { activeBorderColor: "#ef6a4c", hoverBorderColor: "#cc5136" }
        }
      }}
    >
      <AntApp>
        <App />
      </AntApp>
    </ConfigProvider>
  </React.StrictMode>
);

