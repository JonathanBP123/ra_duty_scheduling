# RA Duty Scheduler

This repository contains scripts to help automate RA (Resident Assistant) duty scheduling for a university residence hall. The pipeline includes **two main scripts**: `csv_transformer.py` to prepare RA preference data, and `scheduler.py` to generate a fair, balanced schedule based on those preferences.

---

## **Table of Contents**

- [Overview](#overview)  
- [Installation](#installation)  
- [Usage](#usage)  
  - [csv_transformer.py](#csv_transformerpy)  
  - [scheduler.py](#schedulerpy)  
- [How It Works](#how-it-works)  
- [Outputs](#outputs)  

---

## **Overview**

1. **csv_transformer.py**  
   - Processes raw RA preference data from a Google Sheet export or CSV.  
   - Ensures all necessary columns are present (weekday preferences, block scheduling, blackout dates, weekend unavailability).  
   - Fills in any missing “weekend unavailable” fields with realistic defaults if needed.  

2. **scheduler.py**  
   - Uses OR-Tools constraint programming to assign shifts.  
   - Balances the following:
     - Primaries vs secondaries
     - Weekend primaries vs weekend secondaries
     - Block scheduling preference
     - Day-of-week and blackout preferences  
   - Produces CSV output in a **date-row format**:  
     ```
     date,NE1_primary,NE2_primary,NE1_secondary,NE2_secondary
     ```

---

## **Installation**

1. Make sure you have **Python 3.9+** installed.  
2. Install required packages using pip: `pip install ortools`
3. Optionally, if working with Google Sheets CSV exports, ensure your CSV has the following columns: `First Name, Last Name, Sunday's, Monday's, Tuesday's, Wednesday's, Thursday's, Preference for NE1 vs NE2?, Preference for block scheduling?, Are there any weeks/weekdays during the quarter that you can not work?, What weekend shifts can you not work?`

## **Usage**
1. csv_transformer.py
Transforms and fills in missing preference data.
`python csv_transformer.py --input raw_preferences.csv --output processed_preferences.csv`
* `--input`: Path to raw CSV export from Google Sheets
* `--output`: Path to save the processed CSV that `scheduler.py` will use

2. scheduler.py
Generates a balanced RA schedule.
`python scheduler.py --prefs processed_preferences.csv --outdir ./output`
* `--prefs`: Path to processed RA preferences CSV
* `--outdir`: Directory where `schedule.csv` and `schedule_metrics.csv` will be saved

## **How It Works**
1. Load Preferences
* `load_preferences()` reads the CSV and stores:
  * Daily preferences (Sunday–Thursday)
  * Area preference (NE1 vs NE2)
  * Block scheduling preference
  * Blackout dates & weekend unavailability
2. Build Schedule (`build_schedule()`)
* Constructs a list of all shifts (Sun–Thu weekdays + Fri–Sat weekends).
* Defines binary decision variables for each RA × shift.
* Adds constraints:
  * Exactly one RA per shift
  * No RA works more than 1 shift per day
  * Respect blackout dates and unavailable weekends
  * Do not assign on “Not Available” days
* Adds fairness constraints:
  * Tries to balance total primaries, secondaries, weekend primaries, and weekend secondaries among all RAs
  * Minimizes max–min spread for each shift type
* Encourages block scheduling if RA requested consecutive shifts
* Uses OR-Tools CP-SAT solver to maximize fairness + block scheduling
3. Save Outputs (`save_outputs()`)
* `schedule.csv` — date-row format for calendar import:
```
date,NE1_primary,NE2_primary,NE1_secondary,NE2_secondary
```
* `schedule_metrics.csv` — per-RA shift counts (primaries, secondaries, weekend primaries, weekend secondaries)
* Prints a summary of total shifts and distribution

## **Outputs**
* `schedule.csv` example:
```
date,NE1_primary,NE2_primary,NE1_secondary,NE2_secondary
2025-09-21,Kailie,Oriname,Anna,Fauzan
2025-09-22,Sydney,Parker,Maija,Jonathan
...
```
* `schedule_metrics.csv` example:
```
first_name,primaries,secondaries,weekend_primaries,weekend_secondaries
Kailie,10,8,0,0
Oriname,10,10,6,4
...
```