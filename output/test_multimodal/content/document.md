## Technical Document

## Niagara Histories Guide

September 15, 2022

<!-- image -->

## C Cont tent ts on en s

| About this Guide.................................................................................................7                                  |
|-----------------------------------------------------------------------------------------------------------------------------------------------------|
| Document change log ................................................................................7                                               |
| Related Documents....................................................................................8                                              |
| Chapter 1 About histories ................................................................................9                                         |
| About the history process.........................................................................10                                                |
| About history names ................................................................................11                                              |
| About history policies...............................................................................13                                             |
| About history grouping ............................................................................14                                               |
| About delta logging .................................................................................15                                             |
| About sampling........................................................................................16                                            |
| About security history ..............................................................................17                                             |
| Audit trail management............................................................................18                                                |
| About editing history data........................................................................18                                                |
| Chapter 2 Common history tasks....................................................................21                                                |
| Adding a history extension to a component...............................................21                                                          |
| Configuring a history extension ................................................................21                                                  |
| Configuring rollover properties for delta logging.......................................22                                                          |
| Using relative history extension Ords with the HistoryPointList ..................22                                                                |
| Adding a metadata property to a history extension ...................................24                                                             |
| Configuring custom navigation for the history space..................................25                                                             |
| Setting up an alternate navigation tree......................................................27                                                     |
| Creating History Nav Shortcuts.................................................................28                                                   |
| Discovering and matching histories...........................................................28                                                     |
| Editing history data to filter outliers ..........................................................30                                                |
| Viewing a component in live mode............................................................31                                                      |
| Viewing security history data ....................................................................31                                                |
| About exporting and importing histories...................................................33                                                        |
| Setting up NiagaraNetwork history policy .......................................34                                                                  |
| Discovering histories to import .......................................................35                                                           |
| Discovering histories to export .......................................................36                                                           |
| Manually setting up a single history descriptor ................................38                                                                  |
| Setting up to transfer many histories at once...................................39                                                                  |
| Rdb Archive History Provider....................................................................40                                                  |
| Chart example, local data ...............................................................40                                                         |
| Setting up an Rdb Archive History Provider .....................................41                                                                  |
| PX example, local and archive data .................................................42                                                              |
| Batch history capacity...............................................................................43                                             |
| Updating the capacity property of multiple local histories ................43                                                                       |
| Updating the capacity property of multiple imported histories....................................................................................46 |
| Updating the capacity of remote exported histories ........................48                                                                       |
| Chapter 3 History components.......................................................................51                                               |
| History Property Sheets............................................................................51                                               |

| Audit History Service (history-AuditHistoryService)....................................52                  |
|------------------------------------------------------------------------------------------------------------|
| history-AuditRecord .................................................................................55    |
| history-ConfigRule....................................................................................55   |
| history-ConfigRules ..................................................................................55   |
| history-FoxHistory....................................................................................56   |
| history-FoxHistorySpace...........................................................................58       |
| history-HistoryConfig ...............................................................................58    |
| history-HistoryDevice ...............................................................................59    |
| history-HistoryEditorOptions....................................................................59         |
| history-HistoryId ......................................................................................59 |
| history-HistoryGroup................................................................................60     |
| history-HistoryPointList ............................................................................60    |
| history-HistoryPointListItem .....................................................................61       |
| history-HistoryService ..............................................................................62    |
| history-HistoryShortcuts ...........................................................................63     |
| history-IntervalAlgorithm..........................................................................65      |
| history-LocalDatabaseConfig....................................................................65          |
| history-LogHistoryService.........................................................................65       |
| History extensions....................................................................................68   |
| BooleanChangeOfValue .................................................................70                   |
| BooleanInterval..............................................................................70            |
| NumericInterval .............................................................................70            |
| EnumChangeOfValue .....................................................................70                  |
| EnumInterval..................................................................................70           |
| StringChangeOfValue.....................................................................70                 |
| StringInterval .................................................................................70         |
| CovAlgorithm ................................................................................70            |
| Chapter 4 History plugins...............................................................................71 |
| workbench-WebChart ..............................................................................71        |
| Chart commands............................................................................74               |
| Chart settings ................................................................................77          |
| Collection Table view ...............................................................................82    |
| Database Maintenance view .....................................................................83          |
| Device Histories View ...............................................................................84    |
| History Chart Builder view ........................................................................84      |
| History Chart view....................................................................................86   |
| History Editor view...................................................................................88   |
| History Extension Manager view...............................................................89            |
| History Group Manager view ....................................................................89          |
| History Group Ux Manager view ...............................................................90            |
| History Slot Sheet view.............................................................................91     |
| History Summary view ..............................................................................92      |
| History Table view....................................................................................92   |
| Live History Chart view.............................................................................94     |
| Nav Container view ..................................................................................95    |
| Niagara History Export Manager view.......................................................95               |

| Niagara History Import Manager view.......................................................98                            |
|-------------------------------------------------------------------------------------------------------------------------|
| Metadata Browser view .......................................................................... 100                    |
| On Demand History view........................................................................ 103                      |
| Index...............................................................................................................107 |

- -Configure the extensions.
- -Use a valid history name (part of the configuration).
- · Storing data involves defining the properties of the history database file. For example, you can customize the name of the database file, define the maximum number of records to save, and choose metadata to add to the records.
- · Archiving data includes importing and exporting (transferring) records from one station to another station. For example, you can limit your local station records to a small number, which you specify while archiving all collected records to another station.

To extend the functionality of the component, you add extensions to a component's Property Sheet. By adding a history extension, you can collect a time-stamped entry in the associated history table for a the real-time value or the status of the component's output. The history palette makes history extensions available.

Figure 3 History extensions in the history palette

<!-- image -->

The history table is not stored as part of the component's data but is a separate collection of data referred to as the 'history.'

## A About t hi istor ry names bou h sto y names

By default, when a history extension is added to a component, a history format default string is set to the following: %parent.name% . This string automatically names any histories with the name of the parent component and appends a sequential number to additional names, as necessary.

For example, a history extension on a NumericWritable component creates the default history name: NumericWritable . Then, another numeric writable receives the same name incremented to NumericWritable1 .

Figure 17 Audit History Service properties

<!-- image -->

To open this Property Sheet, expand Config → Services and double-click on the AuditHistoryService in the Nav tree.

The component is designed to audit all property modifications and all action invocations. These events are subject to audit:

- · Property changed
- · Property added
- · Property removed
- · Property renamed
- · Property reordered
- · Action invoked

## Hi istory Confi ig properti ies

These properties configure the audit function. A separate set under the heading Security Audit History Source applies specifically to security-related events, such as authentication and changes to security-related properties.

| Property      | Value                      | Description                                                                                                                                                                                                                                   |
|---------------|----------------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Enabled       | true or false              | Activates and deactivates use of the component.                                                                                                                                                                                               |
| HistoryConfig |                            | Container for sub-properties used to configure the attributes of the history record stored in the History space.                                                                                                                              |
| Id            | Text string                | Read only value. String results from value configured in history extension's History Name property. An error string here indi- cates the History Name property is incorrectly configured .                                                    |
| Time Zone     | display or drop- down list | The time zone is set up using the Set System Date/Time, which you access either using a platform connection and Platform Administration → Change Date/Time or using one of the sta- tion's PlatformServices views (Platform Service Container |

| Property    | Value                                      | Description                                                                                                                                                                                                                                                                                                                                                                                  |
|-------------|--------------------------------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
|             |                                            | plugin or System Date and Time Editor). Otherwise, the time zone is displayed for information only.                                                                                                                                                                                                                                                                                          |
| Record Type | Text                                       | Read only values. Displays the data that the record holds in terms of: extension type ( history ) and data type ( Boolean- TrendRecord NumericTrendRecord , , and so on).                                                                                                                                                                                                                    |
| Capacity    | Record Count: nnn (500 default), Unlimited | Specifies local storage capacity for histories. In general, 500 (default record count) or less is adequate for a controller sta- tion because those records are usually archived (exported) to a Supervisor station. For this reason, a very large number, such as 250,000 is acceptable for Supervisor stations. Unlimited is not the wisest choice even for a Supervisor station.          |
| Full Policy | Roll (default), Stop                       | Applies only if Capacity is set to 'Record Count'. Upon speci- fied record count, the oldest records are overwritten by new- est records. Roll ensures that the latest data are recorded. Stop terminates recording when the number of stored records reaches specified history capacity. Full policy has no effect if Capacity is Unlimited .                                               |
| Interval    | Text string                                | Read only value. For Interval-based data collection, the cycle time, or how often the history properties are checked. Any time you change this property, a new history is created (or 'split-off') from the original history because histories with dif- ferent intervals are not compatible.                                                                                                |
| System Tags | Text                                       | This property allows you to assign additional metadata (the System Tag) to a history extension. This identifier is then avail- able for selective import or export of histories using the Niag- ara System History Import or Niagara System History Export option (using the System Tag Patterns). Each System Tag is separated by a semicolon. For example: NorthAmeri- ca;Region1;Cities . |
| Last Record |                                            | Container for read only values for sub-properties that describe attributes of the last recorded change: date/time the last re- cord was made, time zone, and the operation that generated the record, and the user who made the change.                                                                                                                                                      |

## Last Record propert ties s

| Property   | Value     | Description                                |
|------------|-----------|--------------------------------------------|
| Timestamp  | read-only | Reports when the event occurred.           |
| Operation  | read-only | Identifies the type of event.              |
| Target     | read-only | Reports the modified Ord.                  |
| Slot Name  | read-only | Identifies the host IP address.            |
| Old Value  | read-only | Reports the value before the change.       |
| Value      | read-only | Reports the new value.                     |
| User Name  | read-only | Identifies the person who made the change. |