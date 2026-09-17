# SystemLink Domain Concepts

Use these concepts to translate user language into the correct resource and
identifier before choosing commands. Consult the command and filtering
references for supported syntax.

## Resource identity and scope

- A workspace is a data-isolation boundary. Every resource belongs to one
  workspace. Resolve workspace names to IDs before scripted workflows.
- Resource IDs are not display names. Resolve names, aliases, part numbers,
  serial numbers, or email addresses before passing an ID to another command.
- A system is a managed physical or virtual target. Systems Management owns
  connection, operating-system, package, and remote-management data.
- An asset is physical inventory such as an instrument, fixture, controller,
  or device under test. Asset Management owns the instruments assigned to a
  system.

## Assets and systems

- In hardware questions, treat "asset", "device", and "instrument" as asset
  inventory. Treat DMM and device aliases as asset classes. Treat DAQmx as
  software/package data, including when the user asks about its installation,
  capabilities, or version.
- Asset types are `GENERIC`, `DEVICE_UNDER_TEST`, `FIXTURE`, and `SYSTEM`.
  Fixtures are also called slots in scheduling workflows. A DUT or UUT is a
  `DEVICE_UNDER_TEST` asset associated with a product part number.
- An asset can be directly located in a physical location or in a system by
  slot. Its system reference is the system's minion ID, not its alias.
- "Connected asset" means the asset is present and its owning system is
  connected. Connection does not prove that the asset or system is available
  for scheduling.

Common NI instrument model families:

| User intent | Model families |
| --- | --- |
| DMM or digital multimeter | standalone 40xx family |
| SMU or power supply | 41xx |
| Oscilloscope or scope | 51xx, 59xx |
| Waveform, signal, or function generator | 54xx |
| Switch | 25xx, 27xx |
| Analog-input DAQ | 43xx, 44xx |
| Multifunction DAQ | 60xx, 63xx |
| Digital I/O | 65xx |

NI model names commonly contain a hyphen before the family, such as
`NI PXIe-5422`. Prefer the `asset list --model` convenience filter; use an
Asset API expression only when the convenience filter cannot express the
request. Because `--model` is a contains match, use it as a candidate
prefilter for a model family and verify the returned names before treating
every result as that instrument class. For example, keep only model names
containing a standalone 40xx family when answering an all-DMM query:

```bash
slcli asset list --model 40 --connected --format json | \
  jq '[.[] | select(.modelName | test("(^|[^0-9])40[0-9]{2}([^0-9]|$)"))]'
```

## Test data

- A product represents the item being tested and is identified by part number.
- A specification defines expected limits or a functional expectation for a
  product. A test result records one execution. Test steps contain the
  measurements and nested sequences for that execution.
- Query result summaries before retrieving steps unless a result ID is already
  known. Inspect steps to explain why one result passed or failed.
- "Failed tests" includes `FAILED`, `ERRORED`, and `TERMINATED` unless the user
  names a narrower status. It does not automatically include `TIMEDOUT`,
  `SKIPPED`, `CUSTOM`, or active states.

## Alarms and tags

- An alarm instance proves that a monitored condition triggered; an empty
  instance query does not prove that no alarm rule is configured.
- An alarm becomes inactive only after it is cleared and acknowledged. Cleared
  alarms have severity `-1`; higher nonnegative severity is more severe.
- System health requires connection state, current health-tag values, and alarm
  state together. Missing or stale evidence prevents a definitive healthy
  conclusion.
- System tag paths begin with the minion ID. Common health paths end in
  `.Health.CPU.MeanUsePercentage`, `.Health.Memory.UsePercentage`, and
  `.Health.Disk.UsePercentage`.

## Work items and users

- A work item describes test or maintenance work, assignment, schedule, target
  product, and reserved resources. Use the `slcli workitem` command group for
  work-item discovery, creation, scheduling, and lifecycle operations.
- "Free" means no scheduled work item overlaps the requested interval. It does
  not mean connected, present, or unlocked.
- Fields such as `assignedTo`, `requestedBy`, `createdBy`, and `updatedBy`
  contain user IDs. Resolve a supplied name, email, or login before filtering
  or assigning work.

## Files

Files are separate resources. Associations use either direction:

- A resource can store file IDs, such as `fileIds` on assets, products, and
  test results. Retrieve the resource first, then query those file IDs.
- A file can reference its owner through properties, such as
  `properties.minionId` for a system.

Never use a resource ID as a file ID unless the resource data explicitly
contains that same value as a file reference.