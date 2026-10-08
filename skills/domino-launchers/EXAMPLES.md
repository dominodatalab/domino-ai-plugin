# Launcher examples

Result-generation patterns (multi-format files in `/mnt/results/`, a custom `email.html` body, papermill notebook reports) and a complete scoring launcher with its script and configuration.

## Generating Results

### File-Based Results
Any files created in `/mnt/results/` are available as results:

```python
# Save multiple output formats
df.to_csv('/mnt/results/data.csv')
df.to_excel('/mnt/results/data.xlsx')
fig.savefig('/mnt/results/chart.png')
```

### HTML Email Content
Create `email.html` for custom email body:
```python
# Generate HTML for email
html_content = f"""
<html>
<body>
<h1>Report for {args.start_date} to {args.end_date}</h1>
<p>Summary: {summary}</p>
{df.to_html()}
</body>
</html>
"""

with open('/mnt/results/email.html', 'w') as f:
    f.write(html_content)
```

### Rich Reports
Use notebooks for rich reports:
```python
# Use papermill to execute parameterized notebook
import papermill as pm

pm.execute_notebook(
    'report_template.ipynb',
    '/mnt/results/report.ipynb',
    parameters={
        'start_date': args.start_date,
        'end_date': args.end_date
    }
)
```

## Example: Scoring Launcher

### Script (score_data.py)
```python
import argparse
import pandas as pd
import joblib

parser = argparse.ArgumentParser()
parser.add_argument('--input-file', required=True)
parser.add_argument('--output-format', default='csv')
args = parser.parse_args()

# Load model
model = joblib.load('/mnt/artifacts/model.joblib')

# Load and score data
df = pd.read_csv(args.input_file)
predictions = model.predict(df)
df['prediction'] = predictions

# Save results
if args.output_format == 'csv':
    df.to_csv('/mnt/results/predictions.csv', index=False)
else:
    df.to_excel('/mnt/results/predictions.xlsx', index=False)
```

### Launcher Configuration
```yaml
name: Score Customer Data
command: python score_data.py --input-file ${input_file} --output-format ${output_format}
parameters:
  - name: input_file
    type: file
    label: Customer Data (CSV)
    required: true
  - name: output_format
    type: select
    label: Output Format
    options: [csv, xlsx]
    default: csv
```
