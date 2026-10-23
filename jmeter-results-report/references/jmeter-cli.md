# JMeter from the command line

GUI mode is for building and debugging a plan. Measuring is always done headless: the GUI's
listeners eat CPU and memory on the same machine that generates load, and the numbers drift.

## The one command

```bash
jmeter -n -t plan.jmx -l results.jtl -j jmeter.log -e -o html/
```

| Flag | Meaning |
|---|---|
| `-n` | non-GUI mode |
| `-t <file>` | the test plan |
| `-l <file>` | where raw results go (`.jtl` / `.csv`) |
| `-j <file>` | JMeter's own log — read it first when a run produces nothing |
| `-e` | build the HTML dashboard after the run |
| `-o <dir>` | dashboard folder — **must not exist or must be empty** |
| `-J name=value` | set a JMeter property, read in the plan with `${__P(name,default)}` |
| `-G name=value` | same, for remote (distributed) engines |
| `-q <file>` | an extra properties file — handy for a whole load profile |
| `-f` | delete the `-l` file and the `-o` folder before starting (JMeter 5.x+) |

On Windows the launcher is `jmeter.bat`; the flags are identical.

## Parameterising the load profile

A plan that hard-codes "50 threads" can only ever run 50 threads. In the Thread Group use:

```
Number of Threads : ${__P(threads,10)}
Ramp-up period    : ${__P(rampup,10)}
Duration (s)      : ${__P(duration,60)}
```

Then `-Jthreads=50 -Jrampup=30 -Jduration=300` changes it without touching the file. To see which
properties a plan accepts:

```bash
grep -o '\${__P([^)]*)}' plan.jmx | sort -u
```

## Building the dashboard from an existing .jtl

When the run already happened (for example the user ran it on their own machine):

```bash
jmeter -g results.jtl -o html/
```

The `.jtl` must be CSV with a header row. `-g` refuses XML results.

## Saving the right columns

`run_jmeter.sh` forces these with `-J`, so `user.properties` cannot silently drop them:

```properties
jmeter.save.saveservice.output_format=csv
jmeter.save.saveservice.print_field_names=true
jmeter.save.saveservice.timestamp_format=ms
jmeter.save.saveservice.response_message=true
jmeter.save.saveservice.assertion_results_failure_message=true
```

`timestamp_format=ms` matters: a human-readable timestamp breaks both the dashboard and
`analyze_jtl.py`.

## Listeners in the plan

Remove or disable **View Results Tree**, **Summary Report** and **Aggregate Report** before a
real run — in non-GUI mode they still collect data and slow the load generator down. The `-l`
file already has everything; the dashboard and `analyze_jtl.py` compute the aggregates from it.

## Failure modes

| Symptom | Usual cause |
|---|---|
| `Cannot write to '…/html' as folder is not empty` | the `-o` folder exists. Use a new folder per run (the script does) or `-f` |
| `results.jtl` empty, exit code 0 | every thread failed to start: a missing CSV Data Set file, a JDBC driver not in `lib/`, a plugin not installed. Read `jmeter.log` |
| `CannotResolveClassException` in the log | the plan uses a plugin (e.g. Custom Thread Groups) not installed here — install it via Plugins Manager or `lib/ext` |
| `-J` value ignored | the plan does not read it with `${__P(name)}`, or the name differs in case |
| dashboard: `Mismatch between expected number of columns` | the `.jtl` was written with different save settings than the current `user.properties`; regenerate with the same settings or re-run |
| 100 % errors, `Non HTTP response code: java.net.UnknownHostException` | the target host is not reachable from this machine (proxy, VPN, typo) |
| many `429` / `503` on a public demo API | rate limiting by the target, not a performance result — lower the load and say so in the report |
| JDBC sampler: `No suitable driver` | the driver `.jar` (e.g. `mssql-jdbc`) is not in `$JMETER_HOME/lib` |
| `OutOfMemoryError` | listeners left enabled, or too many threads for the heap: `HEAP="-Xms1g -Xmx2g" jmeter …` |
