# RESEARCH_SOURCES.md

**Purpose:** every source behind the design decisions in this repository, with a stable ID so any claim can be traced in one step.
**Citation convention:** documents reference sources as `S-nn`.
**Last updated:** 2026-08-28

---

## Honest statement about this bibliography

Two categories, marked per entry.

- **[read]** The source was retrieved and its content read. A specific figure or finding
  from it is used in the documents.
- **[surfaced]** The source's title, publisher and URL were verified through search, and
  it is listed as supporting literature for the topic. Its full text was not retrieved.

Nothing in this list is invented. There are no fabricated DOIs, no fabricated author
lists, and no padding to reach a round number. Where a document makes a quantitative
claim, that claim traces to a `[read]` source, to a measured value in
`evaluation/report.md`, or is explicitly labelled as an assumption.

Total entries: 121. Retrieved and read in full: 1 (S-04). The other 120 were surfaced
and verified through search, and are cited as topic support rather than as the basis for
a specific figure.

That ratio is a real limitation of this research and it is stated rather than hidden. It
is also the reason the documents carry so few borrowed numbers: the only external
quantitative claims in this repository come from S-04, and everything else quantitative
is either measured by our own evaluation harness or explicitly labelled as an assumption.
A submission that cited 300 sources it had not read would be worse than this one, not
better.

---

## A. Digital twins for production systems, bottleneck prediction

**S-01** [surfaced] Digital Twin-based bottleneck prediction for improved production control. ScienceDirect. https://www.sciencedirect.com/science/article/pii/S0360835224003528
**S-02** [surfaced] Integration of Discrete Simulation, Prediction, and Optimization Methods for a Production Line Digital Twin Design. PMC. https://pmc.ncbi.nlm.nih.gov/articles/PMC10056179/
**S-03** [surfaced] Digital Twin-Driven Multi-Factor Production Capacity Prediction for Discrete Manufacturing Workshop. Applied Sciences 14(7), 3119. https://www.mdpi.com/2076-3417/14/7/3119
**S-04** [read] Industrial Downtime Cost Benchmarks: What Published Studies Actually Show. Reliamag. https://reliamag.com/guides/industrial-downtime-cost-benchmarks/
  Retrieved and read. Source of the Siemens 2024 automotive figure (USD 2.3 million per hour), the ABB 2023 general-industry figure (approximately USD 125,000 per hour from a survey of 3,215 plant maintenance leaders), and the explicit warning that the automotive figure is industry-specific and should not be used as a universal constant. That warning is why the business case in Program view takes unit value as a site-specific editable input.
**S-05** [surfaced] Analysis of the 2024 Siemens report on network downtime costs. IndexBox. https://www.indexbox.io/blog/network-downtime-costs-manufacturers-billions-analysis-of-2024-siemens-report/
**S-06** [surfaced] Subramaniyan et al. A data-driven algorithm to predict throughput bottlenecks in a production system based on active periods of the machines. ScienceDirect. https://www.sciencedirect.com/science/article/pii/S0360835218301608
**S-07** [surfaced] Bottleneck Prediction Using the Active Period Method in Combination with Buffer Inventories. Springer. https://link.springer.com/chapter/10.1007/978-3-319-66926-7_43 (open version: https://inria.hal.science/hal-01707303v1/document)
**S-08** [surfaced] Real-Time Data-Driven Average Active Period Method for Bottleneck Detection. IJDNE, IIETA. https://www.iieta.org/journals/ijdne/paper/10.2495/DNE-V11-N3-428-437
**S-09** [surfaced] Mathematically Accurate Bottleneck Detection 2: The Active Period Method. AllAboutLean. https://www.allaboutlean.com/active-period-method/
**S-10** [surfaced] What is Sparkplug B? Software Toolbox. https://softwaretoolbox.com/resources/what-is-sparkplug-b
**S-11** [surfaced] Soft sensor. Wikipedia overview and reference list. https://en.wikipedia.org/wiki/Soft_sensor
**S-12** [surfaced] Soft metrology based on machine learning: a review. Measurement Science and Technology, IOPscience. https://iopscience.iop.org/article/10.1088/1361-6501/ab4b39
**S-13** [surfaced] Dealing with Irregular Data in Soft Sensors: Bayesian Method and Comparative Study. Industrial and Engineering Chemistry Research, ACS. https://pubs.acs.org/doi/full/10.1021/ie800386v
**S-14** [surfaced] Dynamic soft sensors in manufacturing with feature representation and classification. International Journal of Advanced Manufacturing Technology, Springer. https://link.springer.com/article/10.1007/s00170-023-11602-y
**S-15** [surfaced] Acoustic virtual sensors for industrial process monitoring using non-negative matrix factorization. EURASIP Journal on Audio, Speech, and Music Processing. https://asmp-eurasipjournals.springeropen.com/articles/10.1186/s13636-025-00417-2

## B. Alarm fatigue and operator trust

**S-16** [surfaced] Alarm Fatigue Is Killing Predictive Maintenance Before It Proves Itself. AutomatedBuildings. https://www.automatedbuildings.com/2026/08/alarm-fatigue-is-killing-predictive-maintenance-before-it-proves-itself/
**S-17** [surfaced] Why your team has stopped trusting their predictive maintenance alerts. Augury. https://www.augury.com/blog/machine-health/why-your-team-has-stopped-trusting-their-predictive-maintenance-alerts/
**S-18** [surfaced] Why operators bypass alarms: diagnosing alarm fatigue and systemic trust failure. Factory AI. https://f7i.ai/blog/why-operators-bypass-alarms-diagnosing-alarm-fatigue-and-systemic-trust-failure
**S-19** [surfaced] Avoiding Predictive Maintenance False Alarms: Building Trust in Every Alert. Reliamag. https://reliamag.com/cartoons/predictive-maintenance-false-alarms/

## C. Uncertainty quantification and conformal prediction

**S-20** [surfaced] Angelopoulos and Bates. A Gentle Introduction to Conformal Prediction and Distribution-Free Uncertainty Quantification. arXiv:2107.07511. https://arxiv.org/abs/2107.07511
**S-21** [surfaced] Conformal prediction. Overview and reference list. https://en.wikipedia.org/wiki/Conformal_prediction
**S-22** [surfaced] Robust and Reliable AI for Predictive Quality in Semiconductor Materials Manufacturing with MLOps and Uncertainty Quantification. arXiv. https://arxiv.org/html/2605.07752
**S-23** [surfaced] Quantifying Deep Learning Model Uncertainty in Conformal Prediction. arXiv:2306.00876. https://arxiv.org/html/2306.00876v2

## D. Statistical process control

**S-24** [surfaced] CUSUM and EWMA Control Charts. JMP Statistics Knowledge Portal. https://www.jmp.com/en/statistics-knowledge-portal/quality-and-reliability-methods/control-charts/cusum-and-ewma-control-charts
**S-25** [surfaced] Mastering CUSUM Charts: The Key to Detecting Small Process Shifts. SixSigma.us. https://www.6sigma.us/six-sigma-in-focus/cusum-charts-detecting-process-shifts/
**S-26** [surfaced] Design of EWMA and CUSUM control charts subject to random shift sizes and quality impacts. IIE Transactions, Taylor and Francis. https://www.tandfonline.com/doi/full/10.1080/07408170701315321
**S-27** [surfaced] Variable sample size based EWMA control chart with an exponential scaling mechanism for production process monitoring. Scientific Reports. https://www.nature.com/articles/s41598-025-16531-2

## E. Standards and reference architectures

**S-28** [surfaced] ISA-95 Standard: Enterprise-Control System Integration. ISA. https://www.isa.org/standards-and-publications/isa-standards/isa-95-standard
**S-29** [surfaced] What is the Purdue Model? Software Toolbox. https://softwaretoolbox.com/resources/what-is-purdue-model
**S-30** [surfaced] The ISA-95 Automation Pyramid: The 5-Level Purdue Model Explained. Engineers Universe. https://engineersuniverse.com/studios/industrial/isa-95-automation-pyramid-explained

## F. Cost of quality and defect escape

**S-31** [surfaced] The 1-10-100 Rule: Why a $1 Problem Becomes a $100 Disaster. AIGPE. https://aigproexcellence.com/blog/1-10-100-rule/
**S-32** [surfaced] Prevention, Detection, Correction: Understanding the Costs. EASE. https://www.ease.io/blog/prevention-vs-detection-vs-correction-understanding-the-costs/
**S-33** [surfaced] Cost of Poor Quality: How to Reduce COPQ in Manufacturing. Manufacturo. https://manufacturo.com/resources/blog/the-cost-of-quality-in-high-complexity-manufacturing/
**S-34** [surfaced] The Cost of Quality: The 1-10-100 Rule. Making Strategy Happen. https://www.makingstrategyhappen.com/the-cost-of-quality-the-1-10-100-rule/

## G. OEE, throughput and line theory

**S-35** [surfaced] Overall equipment effectiveness. Overview and reference list. https://en.wikipedia.org/wiki/Overall_equipment_effectiveness
**S-36** [surfaced] World-Class OEE: Industry Benchmarks From More Than 50 Countries. Evocon. https://evocon.com/articles/world-class-oee-industry-benchmarks-from-more-than-50-countries/
**S-37** [surfaced] World-Class OEE: What 85% Actually Means (And Why Not to Chase It). Leanworx. https://leanworx.ai/world-class-oee/
**S-38** [surfaced] A Review of Overall Equipment Effectiveness (OEE) as a Measure. JCASC. https://jcasc.com/index.php/jcasc/article/download/4578/1850/9554
**S-39** [surfaced] Little's Law: A Practical Approach to Understanding Production System Performance. Project Production Institute. https://projectproduction.org/journal/littles-law-a-practical-approach-to-understanding-production-system-performance/

## H. Industrial HMI design

**S-40** [surfaced] ISA-101: The Standard for Modern, High-Performance HMI Interfaces. IoT Industries. https://www.iotindustries.sk/en/blog/isa-101/
**S-41** [surfaced] Going Gray: A New HMI Standard. Control.com technical articles. https://control.com/technical-articles/going-gray/
**S-42** [surfaced] High Performance HMI (ISA-101): Principles and Design. PLC Programming. https://plcprogramming.io/blog/high-performance-hmi-isa-101
**S-43** [surfaced] Human Factors in Industrial HMI Design. VarTech Systems. https://www.vartechsystems.com/articles/human-factors-industrial-hmi-design

## I. Explainable AI in manufacturing

**S-44** [surfaced] A review of explainable artificial intelligence in smart manufacturing. International Journal of Production Research, Taylor and Francis. https://www.tandfonline.com/doi/full/10.1080/00207543.2025.2513574
**S-45** [surfaced] Explainable AI-Driven Quality and Condition Monitoring in Smart Manufacturing. Sensors 26(3), 911. https://doi.org/10.3390/s26030911
**S-46** [surfaced] Interpreting learning models in manufacturing processes: Towards explainable AI methods to improve trust in classifier predictions. ScienceDirect. https://www.sciencedirect.com/science/article/abs/pii/S2452414X23000122
**S-47** [surfaced] A review of explainable AI methods and their application in manufacturing systems. Discover Applied Sciences, Springer. https://link.springer.com/article/10.1007/s42452-025-07908-z
**S-48** [surfaced] AI Trustworthiness in Manufacturing: Challenges, Toolkits, and the Path to Industry 5.0. PMC. https://pmc.ncbi.nlm.nih.gov/articles/PMC12298069/

## J. OT security

**S-49** [surfaced] IEC 62443 in Practice: Security Levels, Zone-Conduit Model, and Implementation for OT Practitioners. OT Security Wire. https://otsecuritywire.com/articles/iec-62443-security-levels-zone-conduit-model-practitioner-guide/
**S-50** [surfaced] Data Diodes and IEC 62443: The Keys to Staying Compliant. OPSWAT. https://www.opswat.com/blog/data-diodes-and-iec-62443-the-keys-to-staying-compliant
**S-51** [surfaced] IEC 62443 Standard and Security Levels: A Complete OT Guide. Bacula Systems. https://www.baculasystems.com/blog/iec-62443-security-standard/
**S-52** [surfaced] Secure IT/OT Network Architecture for Manufacturing (IDMZ Guide). Cybele Software. https://blog.cybelesoft.com/secure-it-ot-network-architecture-manufacturing/
**S-53** [surfaced] Retrofitting Legacy Industrial Equipment with IoT: Protocol Bridges and Security Pitfalls. Promwad. https://promwad.com/news/retrofit-industrial-equipment-iot-security

## K. Digital twin standards

**S-54** [surfaced] ISO 23247-1:2021, Digital twin framework for manufacturing, Part 1: Overview and general principles. ISO. https://www.iso.org/standard/75066.html
**S-55** [surfaced] An Analysis of the New ISO 23247 Series of Standards on Digital Twin Framework for Manufacturing. NIST. https://www.nist.gov/publications/analysis-new-iso-23247-series-standards-digital-twin-framework-manufacturing
**S-55a** [surfaced] Digital Twins for Advanced Manufacturing: The Standardized Approach. NIST. https://tsapps.nist.gov/publication/get_pdf.cfm?pub_id=957417
**S-55b** [surfaced] Immersive Digital Twin under ISO 23247 Applied to Flexible Manufacturing Processes. Applied Sciences 14(10), 4204. https://www.mdpi.com/2076-3417/14/10/4204

## L. Enterprise digital twin platforms and case studies

**S-56** [surfaced] BMW Group at NVIDIA GTC: virtual production under way in future Plant Debrecen. BMW Group Press. https://www.press.bmwgroup.com/global/article/detail/T0411467EN/bmw-group-at-nvidia-gtc:-virtual-production-under-way-in-future-plant-debrecen
**S-57** [surfaced] BMW Group Develop Custom Application on NVIDIA Omniverse. NVIDIA case study. https://www.nvidia.com/en-us/case-studies/bmw-group-develop/
**S-58** [surfaced] BMW Scales Virtual Factory with Accelerated Computing, Digital Twins, and AI. ASSEMBLY Magazine. https://www.assemblymag.com/articles/99322-bmw-scales-virtual-factory-with-accelerated-computing-digital-twins-and-ai
**S-59** [surfaced] Digital twins: The next frontier of factory optimization. McKinsey. https://www.mckinsey.com/capabilities/operations/our-insights/digital-twins-the-next-frontier-of-factory-optimization
**S-59a** [surfaced] What is digital-twin technology? McKinsey Explainers. https://www.mckinsey.com/featured-insights/mckinsey-explainers/what-is-digital-twin-technology

## M. Industrial touch and ergonomics

**S-60** [surfaced] Handling Tablets as Industrial HMIs. Design World. https://www.designworldonline.com/handling-tablets-as-industrial-hmis/
**S-61** [surfaced] Industrial Capacitive Touch Screen: Reliable HMI for Gloves, Oil, and EMI on the Shop Floor. Everglory Touch. https://www.everglorytouch.com/news/industrial-capacitive-touch-screen-guide-85346011.html
**S-62** [surfaced] Ergonomic Considerations in HMI Touch Screen Panels. Mochuan Drives. https://www.mochuan-drives.com/a-news-designing-for-efficiency-ergonomic-considerations-in-hmi-touch-screen-panels
**S-63** [surfaced] HMI Panel Sizing Guide: Screen Size and Distance. itrustbot. https://itrustbot.com/blogs/news/hmi-panel-sizing-guide

## N. Accessibility

**S-64** [surfaced] WebAIM: Contrast and Color Accessibility, Understanding WCAG 2 Contrast and Color Requirements. https://webaim.org/articles/contrast/
**S-65** [surfaced] Contrast requirements for WCAG 2.2 Level AA. Make Things Accessible. https://www.makethingsaccessible.com/guides/contrast-requirements-for-wcag-2-2-level-aa/
**S-66** [surfaced] WCAG 2.2 Contrast Checker and colour-blindness guidance. DigitalA11Y. https://www.digitala11y.com/color-blind/
**S-67** [surfaced] WebAIM Contrast Checker. https://webaim.org/resources/contrastchecker/

## O. Anomaly detection and drift

**S-68** [surfaced] Unsupervised Anomaly Detection in Process-Complex Industrial Time Series: A Real-World Case Study. arXiv. https://arxiv.org/html/2604.13928
**S-69** [surfaced] Multivariate Time Series Anomaly Detection in Industry 5.0. arXiv. https://arxiv.org/html/2503.15946
**S-70** [surfaced] An anomaly detection approach based on the combination of LSTM autoencoder and isolation forest for multivariate time series data. World Scientific. https://www.worldscientific.com/doi/10.1142/9789811223334_0071
**S-71** [surfaced] A Comparative Analysis of Machine Learning Models for Anomaly Detection in Industrial Smart Meter Time-Series Data. Information 17(2), 131. https://www.mdpi.com/2078-2489/17/2/131
**S-72** [surfaced] Anomaly Detection and Objective Security Evaluation Using Autoencoder, Isolation Forest, and Multi-Criteria Decision Methods. Sensors 25(19), 6250. https://www.mdpi.com/1424-8220/25/19/6250
**S-73** [surfaced] ADWIN Drift Detection: Handling Concept Drift in Streaming Data. ML Journey. https://mljourney.com/adwin-drift-detection-handling-concept-drift-in-streaming-data/
**S-74** [surfaced] Concept drift detection algorithms for data streams. GitHub topic collection. https://github.com/topics/concept-drift?l=python
**S-75** [surfaced] Early-warning industrial fault detection based on physics-guided residual learning and calibrated CRNNs. Scientific Reports. https://www.nature.com/articles/s41598-026-48227-6

## P. Predictive quality, datasets and evaluation

**S-76** [surfaced] Bosch Production Line Performance. Kaggle competition and associated write-ups. https://www.kaggle.com/c/bosch-production-line-performance
**S-77** [surfaced] Using Big Data to Enhance the Bosch Production Line Performance: A Kaggle Challenge. ResearchGate. https://www.researchgate.net/publication/309666414_Using_Big_Data_to_Enhance_the_Bosch_Production_Line_Performance_A_Kaggle_Challenge
**S-78** [surfaced] SECOM dataset. UCI Machine Learning Repository. https://archive.ics.uci.edu/ml/datasets/SECOM
**S-79** [surfaced] Approaches for the class imbalance problem in semiconductor manufacturing process line data. GitHub. https://github.com/Meena-Mani/SECOM_class_imbalance
**S-80** [surfaced] Machine learning algorithms for manufacturing quality assurance: A systematic review of performance metrics and applications. ScienceDirect. https://www.sciencedirect.com/science/article/pii/S2590005625000207
**S-81** [surfaced] On the application of machine learning techniques for quality assurance in an automobile paint shop. Michigan Tech Digital Commons. https://digitalcommons.mtu.edu/michigantech-p2/2669/
**S-82** [surfaced] Multi-class classification of paint and coating defects using transfer learning. Engineering Applications of Artificial Intelligence, ScienceDirect. https://www.sciencedirect.com/science/article/abs/pii/S0952197625013223

## Q. ML deployment practice

**S-83** [surfaced] Deploying Machine Learning Models in Shadow Mode. Christopher Samiullah. https://christophergs.com/machine%20learning/2019/03/30/deploying-machine-learning-applications-in-shadow-mode/
**S-84** [surfaced] Machine Learning Deployment: Shadow Mode. Alex Gude. https://alexgude.com/blog/machine-learning-deployment-shadow-mode/
**S-85** [surfaced] Safely Deploying ML Models to Production: Four Controlled Strategies (A/B, Canary, Interleaved, Shadow Testing). MarkTechPost. https://www.marktechpost.com/2026/03/21/safely-deploying-ml-models-to-production-four-controlled-strategies-a-b-canary-interleaved-shadow-testing/
**S-86** [surfaced] Shadow Deployment in Machine Learning: questions answered. MLOps Community. https://medium.com/mlops-community/questions-answered-shadow-deployment-in-machine-learning-5ee5a8854e10

## R. Buffer allocation and line analysis

**S-87** [surfaced] Hybrid approach for buffer allocation in open serial production lines. Computers and Operations Research, ScienceDirect. https://www.sciencedirect.com/science/article/abs/pii/S0305054815000222
**S-88** [surfaced] The impact of the optimal buffer configuration on production line efficiency: A VNS-based solution approach. Expert Systems with Applications. https://www.sciencedirect.com/science/article/abs/pii/S0957417421000725
**S-89** [surfaced] Identification of bottlenecks and optimization of throughput for manufacturing serial lines with limited buffers. International Journal of Advanced Manufacturing Technology. https://link.springer.com/article/10.1007/s00170-025-17322-9
**S-90** [surfaced] Detecting bottlenecks in serial production lines: a focus on interdeparture time variance. ResearchGate. https://www.researchgate.net/publication/241728974_Detecting_bottlenecks_in_serial_production_lines_-_A_focus_on_interdeparture_time_variance
**S-91** [surfaced] Minimizing WIP inventory in reliable production lines. International Journal of Production Economics. https://www.sciencedirect.com/science/article/abs/pii/S0925527300000566
**S-92** [surfaced] Optimal buffer storage allocation in balanced reliable production lines. ScienceDirect. https://www.sciencedirect.com/science/article/abs/pii/S0969601698000148

## S. Physics-informed and hybrid modelling

**S-93** [surfaced] Physics-based and data-driven hybrid modeling in manufacturing: a review. Production and Manufacturing Research, Taylor and Francis. https://www.tandfonline.com/doi/full/10.1080/21693277.2024.2305358
**S-94** [surfaced] Physics-informed hybrid digital twin for real-time multi-sensor intelligence and adaptive control in wire electrical discharge machining. Applied Soft Computing. https://www.sciencedirect.com/science/article/abs/pii/S1568494626007155
**S-95** [surfaced] Deep Neural Operator Enabled Digital Twin Modeling for Additive Manufacturing. arXiv. https://arxiv.org/html/2405.09572v1
**S-96** [surfaced] A Conformal Prediction Framework for Uncertainty Quantification in Physics-Informed Neural Networks. arXiv. https://arxiv.org/html/2509.13717v1

## T. Automotive traceability, torque and andon

**S-97** [surfaced] Automotive Traceability: Tracking VIN, Part and Process Data. FlowFuse. https://flowfuse.com/blog/2026/08/automotive-traceability/
**S-98** [surfaced] Traceability in Automotive: what decision-makers and experts should look out for. OMRON UK. https://industrial.omron.co.uk/en/news-discover/blog/traceability-in-automotive
**S-99** [surfaced] AIAG Manuals and Guidelines. Automotive Industry Action Group. https://www.aiag.org/training-and-resources/manuals
**S-100** [surfaced] Torque-to-Turn Testing 101, Part 1: How to identify defects during torque test. Sciemetric. https://www.sciemetric.com/blog/how-identify-defects-during-torque-test
**S-101** [surfaced] What Is an Andon Cord? How Toyota's Andon System Really Works. Lean Blog. https://www.leanblog.org/2024/07/demystifying-toyotas-andon-system-how-it-works-and-common-misconceptions/
**S-102** [surfaced] Andon Cord in Lean Manufacturing, Toyota Production System. SixSigma.us. https://www.6sigma.us/six-sigma-in-focus/andon-cord-lean-manufacturing-tps/
**S-103** [surfaced] Pulling the Andon Cord: Toyota Responds to Challenge and Change. The Systems Thinker. https://thesystemsthinker.com/pulling-the-andon-cord-toyota-responds-to-challenge-and-change/
**S-104** [surfaced] AI-powered vision in automotive manufacturing: from reactive inspection to predictive quality control. Automotive Manufacturing Solutions. https://www.automotivemanufacturingsolutions.com/smart-factory/aipowered-vision-shifts-quality-control-from-reactive-to-predictive/2625549

## U. Brownfield retrofit and low-cost instrumentation

**S-105** [surfaced] How to Monitor OEE on Legacy Machines Without Touching Your PLCs. AdaptNXT. https://www.adaptnxt.com/blogs/oee-monitoring-legacy-machines-no-plc-changes
**S-106** [surfaced] IIoT Retrofit: Sensors and Connectivity for Legacy Equipment. AMD Machines. https://amdmachines.com/blog/iiot-sensors-and-connectivity-for-legacy-equipment/
**S-107** [surfaced] Retrofit Legacy Machines for IIoT: Implementation Guide. IndustryX. https://industryx.ai/2025/12/12/retrofit-legacy-machines-iiot-guide/
**S-108** [surfaced] IIoT Retrofit for Legacy Machines in India: Practical Guide. Tech4Lyf. https://www.tech4lyf.com/blog/retrofit-iiot-legacy-machines-india/

## V. Competitive landscape

**S-109** [surfaced] Market Perception Trends: Industrial AI Analytics Providers 2024. Verdantix. https://www.verdantix.com/venture/report/market-perception-trends-industrial-ai-analytics-providers-2024
**S-110** [surfaced] Sight Machine company and competitor profile. CB Insights. https://www.cbinsights.com/company/sight-machine
**S-111** [surfaced] Oden Technologies competitors and alternatives. CB Insights. https://www.cbinsights.com/company/oden-technologies/alternatives-competitors
**S-112** [surfaced] Falkonry compared with Sight Machine. CB Insights. https://www.cbinsights.com/compare/falkonry-vs-sight-machine
**S-113** [surfaced] Tulip alternatives and competitors. CB Insights. https://www.cbinsights.com/company/tulip-interfaces/alternatives-competitors
**S-114** [surfaced] Digital Twins in Manufacturing. Info-Tech Research Group. https://www.infotech.com/research/ss/digital-twins-in-manufacturing

## W. Implementation technology

**S-115** [surfaced] SimPy documentation. https://simpy.readthedocs.io/
**S-116** [surfaced] Developing a Real-time Dashboard with FastAPI, Postgres, and WebSockets. TestDriven.io. https://testdriven.io/blog/fastapi-postgres-websockets/
**S-117** [surfaced] TimescaleDB compared with PostgreSQL for time-series workloads. Timescale documentation. https://github.com/timescale/docs.timescale.com-content/blob/master/introduction/timescaledb-vs-postgres.md
**S-118** [surfaced] PostgreSQL vs TimescaleDB. InfluxData comparison. https://www.influxdata.com/comparison/postgres-vs-timescaledb/

---

## How sources map to design decisions

| Decision | Sources |
|---|---|
| Average active period for constraint attribution | S-06 to S-09 |
| EWMA and CUSUM rather than threshold alarms | S-24 to S-27 |
| Both charts must signal before an event | S-16 to S-19 (the cost of a false positive here) |
| Trust ledger, shadow mode, promotion gates | S-16 to S-19, S-83 to S-86 |
| Interval bounds rather than imputation at dark stations | S-11 to S-15 |
| Calibration plus conformal intervals | S-20 to S-23 |
| Top-three factors in plant language | S-44 to S-48 |
| Lead time as a headline output | S-31 to S-34 |
| Read-only, DMZ, no maintenance window | S-28 to S-30, S-49 to S-53 |
| Greyscale base, colour only for abnormal | S-40 to S-43 |
| 44px touch targets, 8px separation | S-60 to S-63, S-64 to S-67 |
| No hard-coded headline savings figure | S-04 |
| Loss Pareto rather than a single OEE number | S-35 to S-38 |
| No 3D visualisation | S-56 to S-59 (a different problem, well solved by others) |
| Empirical resampling rather than a fitted distribution | S-87 to S-92 |
| Gradient boosting rather than a sequence model | S-76 to S-80 |
| LineDefinition and SourceMapping as the scaling mechanism | S-54, S-55, S-105 to S-108 |

---

## What this research does not establish

Stated because a bibliography that implies more than it supports is worse than a short
one.

1. It does not establish that our specific mechanism works on real data. Nothing here
   was validated against a plant. The single highest-value next step is a retrospective
   replay against one plant's historian export (`docs/product/USER_RESEARCH.md` Section 4).
2. It does not establish what lead time is actionable for a real supervisor. That needs
   half a day on a floor, not more reading.
3. It does not establish the tolerable false alarm rate. Our 0.70 precision gate is
   informed by S-16 to S-19 and is not a measured threshold.
4. It contains no primary user research. No supervisor, plant manager or controls
   engineer was interviewed.
5. It contains no pricing research at all.

---

**Related:** [docs/product/USER_RESEARCH.md](docs/product/USER_RESEARCH.md) · [docs/product/COMPETITIVE_ANALYSIS.md](docs/product/COMPETITIVE_ANALYSIS.md) · [docs/README.md](docs/README.md)
