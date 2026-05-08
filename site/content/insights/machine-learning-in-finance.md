---
title: "Machine Learning in Finance: What Actually Works (and What's Mostly Hype)"
slug: "machine-learning-in-finance"
summary: "Tree-based models can extract real signal from financial data that linear factors miss. Deep nets help less than the marketing implies. Here's the honest map of the territory."
date: "2026-05-08"
author: "TradeWave Research"
reading_minutes: 11
tags: ["machine-learning", "ai", "academic", "factor-models"]
featured: true
related: ["backtesting-pitfalls", "post-earnings-drift", "reading-patterns-without-fooling-yourself"]
---

The pitch is irresistible. A field with mountains of historical data, billions of dollars at stake, and a cottage industry of researchers searching for patterns that beat the market. Why would machine learning, which crushed image recognition and large-language modeling, not also crush finance? The honest answer is that ML does help in finance, but in narrower ways than the marketing implies. Tree ensembles and shrinkage methods extract real signal that linear factor models miss. Deep neural networks add a smaller marginal improvement than their reputation suggests. And the popular fantasy of "feed prices into an LSTM, get rich" has been tested thousands of times by serious people and almost never holds up out of sample.

The anchor paper for what actually works is Gu, Kelly and Xiu (2020), "Empirical Asset Pricing via Machine Learning", published in the Review of Financial Studies. They run a horse race across linear regression, regularized linear methods, random forests, gradient-boosted trees, and several flavours of neural network, predicting monthly returns for individual US stocks using around 94 firm-level characteristics over roughly 60 years of data. Their headline result: tree-based and neural-net methods roughly double the out-of-sample R-squared versus OLS. The level is still small (out-of-sample monthly R-squared on the order of 0.4%), but multiplied across thousands of stocks it translates into economically meaningful long-short portfolio Sharpe ratios well above naive benchmarks.

That paper is the cleanest existing evidence on the question of whether ML earns its keep in cross-sectional return prediction. Almost everything else in the practitioner literature can be evaluated against its findings.

## What works: tree ensembles

Random forests and gradient-boosted trees (XGBoost, LightGBM, CatBoost) are the workhorses of practical financial ML. They handle non-linearities and feature interactions natively, they tolerate noisy data, they do not require careful feature scaling, and they expose interpretability tools (SHAP values, partial dependence plots) that satisfy risk committees. In the Gu, Kelly, Xiu horse race, gradient-boosted regression trees deliver the largest out-of-sample R-squared improvement over OLS among all methods tested. Random forests are close behind.

The intuition for why trees work: factor data is full of conditional relationships. Value works in some regimes but not others. Momentum interacts with volatility. Small-cap effects depend on liquidity conditions. A linear model is forced to assume these relationships are additive and constant. A tree ensemble can carve up the feature space, learn that "high momentum and low volatility together" is a different signal than either ingredient alone, and apply different rules in different parts of the feature distribution.

## What works: regularized linear models

When the feature space is high-dimensional (the so-called "factor zoo" of 300-plus published characteristics), ordinary least squares overfits violently. Lasso (L1 regularization) and Elastic Net (L1 plus L2) impose shrinkage that keeps only the features that actually carry signal in-sample, with strong out-of-sample stability. Bryzgalova, Pelger and Zhu (2023), "Forest through the Trees", uses tree-based methods specifically to prune the factor zoo, identifying the small subset of characteristics that survives serious testing. The intersection of tree-based ML and shrinkage methods is now standard in serious quant shops.

The honest framing: shrinkage methods do not discover new alpha. They do efficient variable selection in environments where the analyst has many candidate predictors and limited data. That is exactly the situation in equity factor research.

## What works (a little): neural networks

Neural networks help in cross-sectional return prediction, but the marginal gain over gradient-boosted trees is small and the engineering cost is large. In Gu, Kelly and Xiu's horse race, the deepest neural-net architectures (NN5 in their notation) edge out trees on some metrics, but the lift is modest given the additional complexity in training, regularization and hyperparameter tuning.

The case for neural nets in finance is strongest where the input is high-dimensional and structured: text from filings, alternative data with hierarchical structure, or asset images (charts, order-book snapshots) where convolutional layers add value. For tabular factor data, trees are usually the better default. The literature is consistent on this point even as the marketing departments insist otherwise.

<figure><img src="/insights/charts/ml-alpha-vs-factors.svg" alt="Out-of-sample R-squared by ML model class"><figcaption>Out-of-sample monthly R-squared by model class predicting individual stock returns, after Gu, Kelly and Xiu (2020). Tree-based and neural-net methods clearly beat linear baselines, but absolute predictive power remains modest in absolute terms.</figcaption></figure>

## What's mostly hype

The biggest gap between practitioner reality and social-media claims is around deep learning on raw price data. LSTM, RNN, transformer architectures applied to time-series of OHLC prices: the literature is full of papers reporting impressive in-sample results that do not replicate out-of-sample. The few replications that do hold up tend to use feature-engineered inputs (returns, volatility, volume ratios) that are functionally similar to the engineered factors a tree model would consume; the recurrent architecture itself is doing little of the work.

Three specific failure modes recur:

First, the social-media "I trained an LSTM on Tesla and it predicts prices" demos almost always have look-ahead bias (the test set leaks into the training set), no transaction-cost modelling, and no out-of-sample validation across regimes. They are the ML equivalent of in-sample curve fitting.

Second, GAN and synthetic-data approaches that augment financial training sets are still research-stage. The fundamental challenge is that synthetic data carries the assumptions of its generator; if the generator could not predict regime breaks, neither can the augmented dataset.

Third, "alternative data" claims should be evaluated on the same criteria as any other signal. Satellite parking-lot imagery, credit-card transaction feeds, web-scraped sentiment: some of these contain real signal, some do not, and most of them have been arbitraged thin by the time retail platforms package them. The question to ask is the same as for any factor: how many independent samples did your test rely on, what was the out-of-sample t-statistic, and how does the alpha decay with assets-under-management?

## Why ML helps in finance

The cases where ML genuinely outperforms simpler methods share a structure: many cross-sectional features (hundreds of stock characteristics), non-linear interactions among those features, and time-varying relationships that classical static models cannot capture. In these settings, ML is doing what it does well: efficient pattern recognition over a feature space too high-dimensional for an analyst to specify by hand.

The Gu, Kelly, Xiu paper makes this concrete. Their feature set has 94 firm-level characteristics interacted with 8 macroeconomic time-series, producing a high-dimensional input that no linear model can handle without strong regularization. ML fills exactly that gap.

## Why ML cannot magic-bullet finance

Four structural problems limit how much ML can help, and these are the reasons "ML in finance" looks more like a useful tool than a revolutionary breakthrough.

**Signal-to-noise ratio.** Asset prices are dominated by news and noise; the predictable component is small. Compare to image recognition, where every pixel carries strong signal about the object. In finance, even a great model leaves most of the variance unexplained.

**Non-stationarity.** Markets adapt. A predictive pattern that works gets arbitraged away. McLean and Pontiff (2016) document a 58% post-publication decay in average anomaly returns. The data-generating process is changing, sometimes because researchers are observing it.

**Sample size.** A century of monthly equity data is 1,200 observations. By the standards of deep learning on text or images, this is tiny. The risk of overfitting in any high-capacity model is correspondingly large, and the literature on backtest overfitting (Bailey et al., 2014; Lopez de Prado, 2018) applies in spades.

**Transaction costs and capacity.** Every signal has a capacity beyond which it ceases to work, because the trades required to harvest it move the market. Most ML strategies are evaluated on paper returns that ignore the slippage and impact that real-world execution would impose. A model with strong paper alpha can be break-even after costs, especially in less-liquid corners of the market.

## What separates working ML strategies from broken ones

Across the academic and practitioner literature, the discipline that matters more than the model choice is the same discipline that matters in any quantitative research: feature engineering, validation methodology, and regime awareness.

Feature engineering matters because trees and neural nets do not invent factors out of thin air. They combine and reweight what you give them. Researchers who feed in carefully constructed firm-level characteristics (book-to-market, accruals, profitability, momentum at multiple horizons, idiosyncratic volatility) get better results than researchers who feed in raw prices.

Validation methodology matters because, as Lopez de Prado has argued for years, naive k-fold cross-validation leaks information in time-series settings. Walk-forward analysis, combinatorial purged cross-validation, or at minimum a strict embargoed out-of-sample window is required to avoid the multiple-testing trap.

Regime awareness matters because a model trained on 2009 to 2019 saw a uniquely supportive macro environment for risk assets. The same model evaluated on 2022 (where bonds and equities sold off together) tells a different story. Working ML practice tests across regimes, reports performance in each, and downgrades conviction in metrics dominated by a single benign era.

## Practical takeaway

ML is a real tool, especially when you have many cross-sectional features and want to capture non-linear interactions among them. Tree ensembles and regularized linear methods are the workhorses, and they earn their keep against linear baselines in studies as careful as Gu, Kelly and Xiu (2020). Deep neural networks add modest incremental value on tabular factor data and meaningful value on unstructured inputs (text, alternative data) where their architectural priors fit the problem.

The fantasies to discard are "feed prices to an LSTM, get rich" and "GANs will generate the data needed to train AGI for trading". The disciplines to keep are out-of-sample testing, multiple-testing awareness, transaction-cost modelling, and regime-aware validation. The model is the smaller part of the work. The honest validation framework around it is the larger part, and it is what separates ML in finance that compounds capital from ML in finance that produces conference talks.
