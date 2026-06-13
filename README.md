# GNSS Positioning Quality Analyzer

A web application for analyzing GPS positioning quality from RINEX 
observation and navigation files.

**Live demo:** https://gnss-saha.streamlit.app

Built at the Department of Geodesy and Geomatics Engineering,  
University of New Brunswick.

---

## What it does

- Reads RINEX 2 and RINEX 3 GPS observation and navigation files
- Computes Single Point Positioning (SPP) with Klobuchar ionospheric corrections
- Measures positioning accuracy: CEP50, CEP95, RMSE horizontal, RMSE vertical, HDOP, PDOP
- Detects multipath contamination using Code-Minus-Carrier (CMC) analysis
- Assesses signal quality using SNR deviation analysis
- Automatically handles malformed RINEX files from Septentrio receivers
- Generates downloadable PDF quality reports
- Beginner and Advanced display modes

---

## How to use

1. Go to **https://gnss-saha.streamlit.app**
2. Upload a RINEX observation file (GPS measurement file)
3. Upload a RINEX navigation file (satellite orbit file)
4. Enter the known receiver coordinates (latitude, longitude, ellipsoidal height)
5. Click **Analyze session**
6. Download the PDF report

No installation required — runs in any web browser.

---

## Benchmark validation results

| Station | Receiver | CEP50 | HDOP | Interval |
|---|---|---|---|---|
| FRDN (Fredericton NB) | Trimble Alloy | 55.0 m | 1.46 | 30s |
| UNB3 (Fredericton NB) | Trimble Alloy | 75.3 m | 1.30 | 30s |
| JPLM (Pasadena CA) | IGS station | 56.7 m | 1.35 | 30s |
| FRDN (Fredericton NB) | Septentrio PolaRx5 | 23.0 m | 1.23 | 30s |
| GATE (UNB campus) | JAVAD TR-LS2 | 17.5 m | 1.89 | 10s |
| TIMS (UNB campus) | Septentrio Altus | 45.3 m | 1.33 | 1s |

---

## RINEX file compatibility

| Format | Supported |
| RINEX 2 observation | Yes |
| RINEX 3 observation | Yes |
| RINEX 3 navigation | Yes |
| Septentrio high-frequency (10 Hz) | Yes — automatic cleaning |
| Multi-constellation (GPS+GLONASS+Galileo) | Yes — GPS extracted |

---

## Tech stack

| Component | Library |
| Web dashboard | Streamlit |
| RINEX parsing | georinex |
| Numerical computing | NumPy, SciPy |
| Plotting | Matplotlib |
| PDF generation | fpdf2 |
| Deployment | Streamlit Community Cloud |

---

## Project structure
