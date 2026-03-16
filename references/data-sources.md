# 数据源说明

## 1. 币安现货公开产品接口

- Endpoint: `https://www.binance.com/bapi/asset/v2/public/asset-service/product/get-products?includeEtf=true`
- 单资产：`https://www.binance.com/bapi/asset/v2/public/asset-service/product/get-product-by-symbol?symbol=BTCUSDT`

主要用途：

- 获取交易对的价格、开高低收、24h 成交额
- 识别高成交额现货主轴
- 作为聚焦资产分析时的现货补充

## 2. Binance USDⓈ-M Futures 公共接口

- 24h Ticker: `https://www.binance.com/fapi/v1/ticker/24hr`
- Fallback: `https://fapi.binance.com/fapi/v1/ticker/24hr`
- Premium Index: `https://www.binance.com/fapi/v1/premiumIndex`
- Open Interest History: `https://www.binance.com/futures/data/openInterestHist`

主要用途：

- 判断合约热度与成交承接
- 计算资金费率温度
- 计算 5 分钟持仓变化
- 构建“杠杆热层”和“引力坍缩”预警

## 3. Binance Alpha 公开列表

- Endpoint: `https://www.binance.com/bapi/defi/v1/public/wallet-direct/buw/wallet/cex/alpha/all/token/list`

主要用途：

- 获取 Alpha 代币、成交额、流动性、上线时间
- 识别 `mulPoint = 4` 的早期强化信号
- 构建“Alpha 前沿层”

## 4. Binance Web3 社媒热度

- Endpoint: `https://web3.binance.com/bapi/defi/v1/public/wallet-direct/buw/wallet/market/token/pulse/social/hype/rank/leaderboard`

主要用途：

- 捕捉社媒热度最强的代币
- 获取情绪、热度摘要、KOL 数量
- 构建“社媒引力”和“AI 叙事束”

## 5. Binance Web3 统一排行

- Endpoint: `https://web3.binance.com/bapi/defi/v1/public/wallet-direct/buw/wallet/market/token/pulse/unified/rank/list`

主要用途：

- 获取链上价格变化、成交额、流动性、持有人、标签、Alpha 标签
- 获取风险等级与风险代码
- 作为链上资产矩阵的主表

## 6. Binance Web3 聪明钱流入

- Endpoint: `https://web3.binance.com/bapi/defi/v1/public/wallet-direct/tracker/wallet/token/inflow/rank/query`

主要用途：

- 获取 Launchpad / Meme 方向的聪明钱迁跃
- 识别低流动性高热度的匿名冲击
- 构建“Launchpad / 迷因冲击层”

## 7. Binance Web3 智能信号

- Endpoint: `https://web3.binance.com/bapi/defi/v1/public/wallet-direct/buw/wallet/web/signal/smart-money`

主要用途：

- 获取买卖方向、触发价格、当前价格、最大收益、状态
- 构建“聪明钱跃迁层”
- 给聚焦资产补足信号上下文

## 8. Binance 官方公告 CMS

- 列表：`https://www.binance.com/bapi/composite/v1/public/cms/article/list/query`
- 详情：`https://www.binance.com/bapi/composite/v1/public/cms/article/detail/query`

建议关注栏目：

- `48`：New Cryptocurrency Listing
- `49`：Latest Binance News
- `93`：Latest Activities

主要用途：

- 构建官方催化层
- 提取上新、合约、Margin、Earn、API 更新等动作
- 生成广播封包和日内催化摘要
