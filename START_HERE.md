# SiteIQ: start here

## Run it
You need Python 3.10 or newer, and Node.js 20 or newer the first time.

- **Windows:** double-click `run_siteiq.bat`
- **macOS or Linux:** run `./run_siteiq.sh`

The first run installs everything and builds the interface. SiteIQ then opens at http://127.0.0.1:8765 and runs only on your computer.

## Do a study
Work through the sheets on the left. Figures update as you type.

1. **A-01 Site:** paste a Google Maps link, coordinates or an address. Check the point and the suggested authority.
2. **A-02 Boundary:** drop a DXF, KML, KMZ or vector PDF. Choose the plot, set the scale if asked, and click each edge to mark it road, rear or side. Press **Use this boundary**.
3. **A-03 Controls:** choose the authority and land-use category, then enter the road width and where it came from. Mark each site constraint as clear or affecting the site.
4. **A-04 FAR:** see the figure, the matched table bands and the source.
5. **A-05 Options:** enter height and floors for up to four options. Leave the footprint blank to derive it from the envelope and coverage limit.
6. **A-06 Dossier:** read the status and the compliance register, then export.

**L-01 Rule library** shows which authorities have rules, and installs official GIS layers.

## Read the status
| Status | Meaning |
|---|---|
| Blocked | At least one check fails |
| Incomplete | Information is missing, so figures may change |
| Provisional | Nothing fails, but some items could not be confirmed |
| Ready for review | Everything passes on a verified profile. No profile qualifies yet |

## Without Node.js or for the older interface
`python -m streamlit run app.py` starts the Streamlit interface. It uses the same calculations.

## Saving your work
Studies save automatically in your browser and appear under Recent. **Save project file** writes a `.siteiq` file you can back up or send to a colleague. Under **Revisions** on the dossier sheet, save a revision before changing anything to see exactly what moved.

## Sign off a rule profile
After a registered architect has reviewed a profile:
```bash
python -m siteiq.rule_admin validate
python -m siteiq.rule_admin sign-off hoskote_lpa2031_candidate --reviewer "Name, CoA no." --note "What was checked"
```
Update `tests/test_reliability.py` (`test_no_shipped_profile_claims_verified_status`) in the same commit. It is there to stop a profile being marked verified by accident.

## Add an authority
Copy a file such as `rules/hoskote_lpa2031_candidate.json`, enter that plan's tables with their sources, link it in `rules/authority_registry.json` and `rules/authority_coverage_matrix.csv`, then run the validate command.

## Run the tests
```bash
pip install -r requirements-dev.txt
python -m pytest -q
cd frontend && npm test && npx playwright test
```
On a machine with ROS on the Python path, unset `PYTHONPATH` and set `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`. Playwright uses your installed Chrome. Set `SITEIQ_PYTHON` if your environment is not `.venv`.
