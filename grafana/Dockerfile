FROM grafana/grafana-oss:latest

RUN grafana cli --pluginUrl https://github.com/haohanyang/mongodb-datasource/releases/download/v0.3.2/haohanyang-mongodb-datasource-0.3.2.zip plugins install haohanyang-mongodb-datasource

RUN grafana cli plugins install marcusolsson-dynamictext-panel