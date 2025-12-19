# SystemLink 
Enterprise User 
Manual
2025-12-18
![image](images/pdf_image_1_2.png)

SystemLink Enterprise User Manual
Contents 
Contents
SystemLink Enterprise User Manual . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  7 
Overview . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  8 
SystemLink Enterprise Requirements . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  9
SystemLink Client Requirements . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  9
Components of a SystemLink Enterprise System . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  11 
New Features and Changes . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  14 
Updates and Changes for 2024 and Earlier . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  20 
Theory of Operation . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  30 
Examples . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  33 
Navigating SystemLink Enterprise . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  35
Viewing and Editing User Account Settings . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  35 
Filtering Grids . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  37
Installation and Configuration . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  39
Configuring SystemLink Enterprise . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  39
Downloading the Configuration Templates . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  39 
Configuring SystemLink Repositories . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  40 
Configuring Web Access to SystemLink Enterprise . . . . . . . . . . . . . . . . . . . . . . . . . .  41 
Configuring an Elasticsearch Instance . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  42 
Configuring File Storage . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  46
Required Permissions for File Storage . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  55
### Configuring OpenID Connect Client Access . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  59 
Assigning an Initial System Administrator . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  61 
Storing Data from the Dashboard Host Service on an External PostgreSQL 
Server . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  62 
Storing Data from the Test Monitor Service on an External PostgreSQL Server . .  63 
Configuring the Notebook Execution Service . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  65 
Configuring Secrets . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  67 
Configuring Email Notifications . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  68 
Configuring Advanced Search for Files . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  69 
Configuring Dremio . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  70 
Configuring MongoDB Instances . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  71 
Installing Modules . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  76
2
ni.com
SystemLink Enterprise User Manual
Installing the Test Plans Module . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  76 
Installing the Specification Compliance Module . . . . . . . . . . . . . . . . . . . . . . . .  77
Data Limits for Proxy Servers and for Ingress Controllers . . . . . . . . . . . . . . . . . . . . .  77 
Configuring Jupyter Notebook Limits . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  78
Installing SystemLink Enterprise . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  79 
SystemLink Enterprise Network Interactions . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  83
Network Security Considerations . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  86
Private Certificate Authorities . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  88
Updating SystemLink Enterprise . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  90 
Resolving RabbitMQ Cluster Incompatibility . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  92 
Uninstalling SystemLink Enterprise . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  94 
Required Secrets . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  94 
Backing up SystemLink Enterprise . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  105 
Restoring SystemLink Enterprise . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  107 
Resetting Dremio . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  108
Managing Access to SystemLink Enterprise . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  111
Assigning a Server Administrator to a Server . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  111 
Creating a Workspace . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  111 
Configuring a Role and Privileges . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  112
Predefined Roles in SystemLink Enterprise . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  113
Assigning Users to Roles in a Workspace . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  115
Role-Based Access Control Concepts . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  117
Adding Users to a Workspace . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  118 
Archiving Your Workspaces . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  118 
Creating an API Key . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  119
Managing Your Systems . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  120
Setting up a SystemLink Client . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  120 
Modifying the Settings of a System . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  122
Applying Custom Metadata to Systems . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  123 
Changing a System Name . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  124
Queuing Jobs for Offline Systems . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  124 
Visualizing Metadata of a System . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  125 
Generating System Configuration Reports . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  125 
Monitoring System Health with Alarms . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  126
Managing Your Assets . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  131
Viewing Hardware Calibration Data . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  131
© National Instruments 3
SystemLink Enterprise User Manual
Adding Assets . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  132 
Tracking the Location of Assets over Time . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  134 
Applying Custom Metadata to Assets . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  134
Managing Work Orders and Work Items . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  135
Creating and Managing Work Orders . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  135 
Creating a Test Plan . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  136 
Scheduling a Test Plan . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  137 
Viewing Scheduled Test Plans . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  139 
Automating Work Items with Jupyter Notebook . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  140 
Reserving Fixtures for a Test Plan . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  141
Monitoring Tests . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  144
Integrating Test Monitor with TestStand . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  144 
Associating Test Results with a Product . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  146 
Publishing Test Results with the Test Monitor API . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  146 
Analyzing and Interacting with Test Results . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  147
Creating a Product . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  147 
Visualizing Your Test Result Metadata . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  148 
Viewing Test Results by Product . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  148 
Collaborating on Test Results . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  149 
Viewing Test Steps by Result . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  150 
Moving a Test Result to Another Workspace . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  151 
Analyzing Test Results with Jupyter Notebook . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  152 
Visualizing Notebook Data on a Dashboard . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  153
Using Notebook Outputs as Dashboard Variables . . . . . . . . . . . . . . . . . . . . .  153
Visualizing Data Tables in a Dashboard . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  154 
Using Data Tables as Dashboard Variables . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  154 
Interacting with Data in a Data Space . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  155
Visualizing Data Tables in a Data Space . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  155 
Plotting Parametric Data in a Data Space . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  157 
Analyzing Parametric Data in a Data Space . . . . . . . . . . . . . . . . . . . . . . . . . . .  158 
Creating Marginal Plots . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  160 
Annotating Test Results or Steps with Keywords from a Data Space . . . . .  161
Predefined Properties . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  162
Storing and Forwarding Test Data . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  163 
Uploading Custom Files to Test Monitor . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  163
Uploading Custom Files with a VI . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  164
4
ni.com
SystemLink Enterprise User Manual
Uploading Files with a TestStand Step . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  165
Filtering and Sorting Test Results by Custom Properties . . . . . . . . . . . . . . . . . . . . . . . . .  165 
Viewing Out of The Box (OOTB) Dashboards . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  167
Specification Compliance . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  169
Structure of a Specification . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  169 
Adding Specifications to a Product . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  174 
Viewing Specifications for a Product . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  175 
Connecting Test Data to Specifications . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  176 
Deleting Specifications . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  177 
Analyzing Specification Compliance with Jupyter Notebook . . . . . . . . . . . . . . . . . . . . .  177
Sharing Data across Systems . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  179
Storing and Managing Files . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  179
File Formats Supported in File Preview . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  181 
Normalizing Data for Efficient Storage and Access . . . . . . . . . . . . . . . . . . . . . . . . . .  186 
Normalizing Incoming Data Automatically . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  191 
SystemLink Predefined Properties . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  193
Communicating Data with Tags . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  195
Transferring Data Using Tags . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  195 
Monitoring Data with Tags . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  198
Connecting to Clients . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  199
Transferring Files from Disk to SystemLink Enterprise . . . . . . . . . . . . . . . . . . . . . .  200 
Transferring Files from Memory to SystemLink . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  202 
Acquiring Test Results . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  203
Structuring Your Test Data . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  206
Generating Custom Alarms . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  207
Configuring Alarm Retention . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  210 
Configuring Alarm Limits . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  211
Monitoring Alarms . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  213 
Hosting a Web Application . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  213
Automating Actions with Routines . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  216 
Reporting Data with Jupyter Notebooks . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  218
Creating a Notebook in Jupyter Notebooks . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  218 
Creating a Custom Script for Analyzing Parametric Data . . . . . . . . . . . . . . . . . . . . . . . . .  219 
Publishing a Jupyter Notebook . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  222 
Installing Additional Python Modules . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  226 
Viewing Notebook Workflow Details . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  226
© National Instruments 5
SystemLink Enterprise User Manual
Analyzing Files with Jupyter Notebook . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  227 
Extracting Data from Files with Jupyter Notebooks . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  228
Adding Custom Input Fields to the User Interface . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  229
Configuring Dynamic Form Fields . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  230 
Customizing a Dynamic Form Field Configuration . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  232
Service Performance Specifications . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  236
Performance of the Test Monitor API on PostgreSQL . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  236 
Data Extraction Performance for Standard Files . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  256
Service Health Monitoring . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  260
Alarm Service Metrics . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  260 
Alarm Service Routine Executor Metrics . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  262 
Dashboard Host Service Metrics . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  264 
DataFrame Service Metrics . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  266 
Location Service Metrics . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  270 
Tag Service Service Metrics . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  272 
v2 Routine Service Metrics . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  279 
Web Application Service Metrics . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .  281
6
ni.com
SystemLink Enterprise User Manual
SystemLink Enterprise
SystemLink Enterprise  User Manual 
User Manual
The SystemLink Enterprise User Manual provides detailed descriptions of the product 
functionality and the step by step processes for use.
Looking for Something Else?
For information not found in the User Manual for your product, such as specifications 
and API reference, browse Related Information.
Related information:
• Release Notes 
• Installation Guide on GitHub 
• YouTube Channel
© National Instruments 7
SystemLink Enterprise Overview
SystemLink Enterprise
SystemLink Enterprise  Overview 
Overview
SystemLink Enterprise is scalable, self-hosted software for product engineers, 
production engineers, and lab managers working on a large corporate scale. Use 
SystemLink Enterprise to manage your automated test systems, data collection, and 
reporting from a central location.
SystemLink Enterprise Key Features
SystemLink Enterprise has the following features and capabilities.
• Systems management to perform operations such as the following:
◦ Managing system health 
◦ Deploying software to multiple systems at once
• Asset management to track utilization, calibration information, and find assets. 
• A Test Insights application to ingest test data and monitor performance and status. 
• Data tables to normalize data from multiple formats so you can run analyses on all
data in a common format.
• Dashboards to monitor systems and key performance indicators. 
• Jupyter notebooks to automate analysis and the creation of HTML and PDF
reports.
• Routines to trigger Jupyter notebook execution on configurable events or on a
schedule.
• Role-based access control to simplify user management and access to data in a
large organization.
• Kubernetes to manage container life cycle, reliability, and horizontal scaling. 
• Helm charts to simplify installation.
8
ni.com
SystemLink Enterprise Requirements
SystemLink Enterprise
SystemLink Enterprise  Requirements 
Requirements
To use SystemLink Enterprise, your computer must meet certain requirements.
• Latest version of a supported browser:
◦ Chrome 
◦ Firefox 
◦ Edge (Chromium) 
◦ Safari
SystemLink Client Requirements 
SystemLink Client Requirements
To use SystemLink Client to communicate with targets, your targets must meet the 
following requirements.
Hardware Requirements
Table 1. Hardware Requirements for Targets Using SystemLink Client
Component 
Windows 
NI Linux Real-Time
Processor 
Pentium 4 G1 (equivalent or 
better) 
Intel or ARM model
2 GiB minimum
512 MiB minimum
RAM
4 GiB recommended
1+ GiB recommended
1 GB minimum
Disk
2+ GB recommended 
512 MB
Software Requirements
For SystemLink Client software requirements, refer to SystemLink Client and 
External Dependencies Compatibility.
© National Instruments 9
SystemLink Enterprise Requirements
Node Requirements
Table 2. Requirements for a Node Running SystemLink
Component 
Windows 
NI Linux Real-Time
NI Linux Real-Time 2019, 2020, 
2021
OS (64-bit only) 
• Windows 10 (64-bit) 
• Windows 11 (64-bit)
(Supports LabVIEW RT 2019, 
2020, 2021 and NXG 5.0 and 
later)
Processor 
64-bit 
All Intel and ARM models 
supported
RAM 
• 2 GiB minimum 
• 4 GiB recommended
• 512 MiB minimum 
• 1+ GiB recommended
Disk 
• 1 GB minimum 
• 2+ GB recommended 
512 MB recommended
Note SystemLink does not support VxWorks or Phar Lap OS.
Related information:
• SystemLink Client and External Dependencies Compatibility
10
ni.com
Components of a SystemLink Enterprise System
Components of a 
Components of a SystemLink Enterprise 
SystemLink Enterprise
System 
System
SystemLink Enterprise implements a server-client architecture to transmit data over a 
connected network between your systems and server. Use the minimum required 
SystemLink Enterprise system components as a starting point for building your 
system.
For more information on component software that is compatible with your version of 
SystemLink Enterprise, refer to Related information.
Table 3. Minimum Required SystemLink Enterprise System Components
Component 
Description and Recommendations
• A Kubernetes cluster running Kubernetes with Linux worker
nodes.
• Helm to configure and to install the application. 
• Dynamic Volume Provisioning enabled on the cluster.
Note When deploying to an Amazon Web Services 
cluster, use Amazon Elastic Block Store (EBS) 
volumes. SystemLink Enterprise does not support 
Amazon Elastic File Storage (EFS) volumes.
Kubernetes cluster
• An NFS storage provisioner, or equivalent storage class, with
ReadWriteMany access.
• Properly configure the inotify parameters in the Kubernetes
nodes, such as max_user_instances, 
max_user_watches, and max_queued_events.
Note For more information, refer to the 
configuration guide for your Linux distribution.
External data storage
• An Amazon S3 or Amazon S3-like file storage interface.
© National Instruments 11
Components of a SystemLink Enterprise System
Component 
Description and Recommendations
• A PostgreSQL instance or replica set. 
• A MongoDB instance or replica set. 
• An Elasticsearch instance.
• An NGINX Ingress Controller for HTTP communication. 
• DNS and three distinct host names. 
• An identity provider with support for the OpenID Connect
Networking and user 
authentication
protocol.
• Network access to the NI Artifact repository.
SystemLink Client 
Use SystemLink Client to communicate with targets. For more 
information on target requirements, refer to Related information.
Sizing a SystemLink Enterprise Cluster
SystemLink Enterprise runs a minimum of two Kubernetes worker nodes and can scale 
to as many nodes as needed for your organization. To determine specific hardware 
requirements for your deployment, contact your account representative.
For a production deployment, NI encourages administrators to provision enough 
worker nodes to enable a high availability configuration.
Related concepts:
• SystemLink Enterprise Network Interactions 
• Configuring an Elasticsearch Instance
Related tasks:
• Storing Data from the Dashboard Host Service on an External PostgreSQL Server 
• Storing Data from the Test Monitor Service on an External PostgreSQL Server 
• Configuring OpenID Connect Client Access 
• Configuring MongoDB Instances
Related information:
12
ni.com
Components of a SystemLink Enterprise System
• Release Notes 
• SystemLink and External Dependencies Compatibility 
• Installing Helm 
• Dynamic Volume Provisioning 
• NFS Storage Provisioner 
• Taints and Tolerations 
• Kubernetes Access Modes 
• Salt TCP Transport 
• NI Artifact Repository
© National Instruments 13
SystemLink Enterprise New Features and Changes
SystemLink Enterprise
SystemLink Enterprise  New Features and 
New Features and
Changes 
Changes
Learn about updates, including new features and behavior changes, introduced in 
each version of SystemLink Enterprise.
Discover what is new in the latest releases of SystemLink Enterprise.
Note If you cannot find new features and changes for your version, it might 
not include user-facing updates. However, your version might include non-
visible changes such as bug fixes and compatibility updates. For information 
about non-visible changes, refer to your product Release Notes.
Related concepts:
• Updates and Changes for SystemLink Enterprise 2024 and Earlier
Related information:
• Release Notes
November 2025
• Use test plans within work items to track lab operations and resources. For more
information, refer to Managing Work Orders and Work Items.
Related concepts:
• Managing Work Orders and Work Items
October 2025
• Create and manage the locations of your systems and assets in the Locations page. 
• Upload files through chunked transfer encoding using the SystemLink API. 
• Support for binary ingestion in the DataFrame service.
14
ni.com
SystemLink Enterprise New Features and Changes
September 2025
• View all test plans scheduled for a specific system in the System Details page. For
more information, refer to Viewing Scheduled Test Plans.
• Use the Schedule page to search and filter for fixtures. 
• Customize test plan workflows to match the processes of your organization. For
more information, refer to the Test Plan Operations Example page in GitHub.
• Manage system keys to resolve connection and security issues. 
• Use the Assets data source in dashboards to display the total count of returned
assets in a query.
• Compatibility with Grafana 11.
Related tasks:
• Viewing Scheduled Test Plans
Related information:
• Test Plan Operations Example
August 2025
• Support for Server-Side Encryption through the Key Management Service (AWS
SSE-KMS). For more information, refer to Configuring File Storage.
Related concepts:
• Configuring File Storage
July 2025
• Support for hosting SystemLink Enterprise on Microsoft Azure. For more
information, refer to Configuring File Storage.
• Support for full text search on all file types. For more information, refer to
Configuring an Elasticsearch Instance.
• Use out of the box dashboards to access information such as asset calibration, lab
© National Instruments 15
SystemLink Enterprise New Features and Changes
overview, and product test summary. For more information, refer to Viewing Out 
of the Box (OOTB) Dashboards in SystemLink Enterprise.
• Support for the following data sources in dashboards:
◦ Test Plans 
◦ Work Orders 
◦ Test Results
For more information, refer to Visualizing Notebook Data on a Dashboard.
• Filter systems and test plans in schedule view. You can then save these filters and
schedule view configurations as named views. For more information, refer to 
Viewing Scheduled Test Plans.
Related concepts:
• Configuring File Storage 
• Configuring an Elasticsearch Instance
Related tasks:
• Viewing Out of the Box (OOTB) Dashboards in SystemLink Enterprise 
• Visualizing Notebook Data on a Dashboard 
• Viewing Scheduled Test Plans
June 2025
• Use Jupyter Notebook to automatically schedule test plans. For more information,
refer to Automating Test Plans with Jupyter Notebook.
• Use Jupyter Notebook to automate operations on test plans. 
• View fixture details from the Scheduling Assistant page. 
• When either installing software or applying a system state, you can enable the
Automatically Restart option. SystemLink now remembers this selection when the 
action is next taken again.
Related tasks:
• Automating Work Items with Jupyter Notebook
16
ni.com
SystemLink Enterprise New Features and Changes
May 2025
• Use routines to create tag threshold alarms and to send email notifications. For
more information, refer to Monitoring System Health with Alarms.
• Use the Systems grid and the Assets grid to determine if an associated tag has an
active alarm.
• View the details of a fixture while scheduling a test plan. For more information,
refer to Viewing Scheduled Test Plans.
Related tasks:
• Monitoring System Health with Alarms 
• Viewing Scheduled Test Plans
Related reference:
• Alarm Service Routine Executor Metrics 
• v2 Routine Service Metrics
April 2025
• Schedule a test plan to a fixture under a system. A lab might refer to a fixture as a
slot, a socket, or a channel. For more information, refer to Using a Fixture in a 
Test Plan.
• Preview common plain text file formats. For more information, refer to File
Formats Supported in File Preview.
• Save statistical insights from the analysis of parametric data in a data space. 
• Manage alarm instances by navigating to Overview » Alarms. 
• Added support for results and steps in the Test Monitor Python library. For
more information, refer to the Releases ni/systemlink-clients-python page 
on GitHub.
• Added support for virtual systems. Use a virtual system to manually or
programmatically manage any data and assets associated with that virtual system.
• Retry and run new notebook executions from the Executions page. 
• Filter files by file ID. 
• Configure file properties to display in the File Details page.
© National Instruments 17
SystemLink Enterprise New Features and Changes
Related concepts:
• Reserving Fixtures for a Test Plan
Related reference:
• File Formats Supported in File Preview
Related information:
• Releases ni/systemlink-clients-python
March 2025
• Display product data and properties from the Test Monitor backend service in
dashboards.
• Preview your CSV files. 
• Preview your HTML files.
February 2025
• Preview your PDF files. 
• Filter the list of work orders you see based on their status or their metadata and
save custom views. Navigate to Operations » Work Orders and click the summary 
tiles at the top of the page.
• Learn about the performance metrics for the Web Application Service. 
• Enhanced the performance of queries against continuously written data tables. 
• Use Google Cloud Storage (GCS) to store your files.
Related concepts:
• Configuring File Storage
Related tasks:
• Creating and Managing Work Orders
Related reference:
18
ni.com
SystemLink Enterprise New Features and Changes
• Web Application Service Metrics
January 2025
• Use dynamic form fields to add custom input fields to the user interface. You can
add fields to the configuration slide-out of the following resources. 
◦ Assets 
◦ Products 
◦ Systems 
◦ Test Plans 
◦ Work Orders
• Host web applications. 
• Preview your image, audio, and video files. 
• Filter the list of test plans you see based on their status or their metadata. Navigate
to Operations » Work Items and click the summary tiles at the top of the page.
• Adjust the default rate limits for Jupyter Notebook operations.
Related tasks:
• Hosting a Web Application 
• Adding Custom Input Fields to the User Interface 
• Configuring Jupyter Notebook Limits
Related reference:
• File Formats Supported in File Preview
© National Instruments 19
Updates and Changes for SystemLink Enterprise 2024 and Earlier
Updates and Changes for 
Updates and Changes for SystemLink 
SystemLink
Enterprise
Enterprise  2024 and Earlier 
2024 and Earlier
Browse updates and changes made in SystemLink Enterprise 2024 and earlier 
versions.
Note If you cannot find changes for your version, it might be a more recent 
version, documented as a new feature. Or, your version might not have 
included user-facing updates. You can find more information about non-
visible changes, such as bug fixes, compatibility updates, and stability 
adjustments or maintenance adjustments, in the product Release Notes, 
available on ni.com.
Related concepts:
• SystemLink Enterprise New Features and Changes
Related information:
• Release Notes
2024
December 2024
• Analyze your parametric data in a Data Space to get statistical insights. 
• Create a custom script to analyze your parametric data in a Data Space. 
• Use the keyboard to interact with grids. For example, you can use the arrow keys to
navigate to different rows and different columns.
• Add a hyperlink to an external URL as the value of a custom property. Use the
following syntax similar to Markdown: `[link text](URL)`.
• View additional details about a test plan from the Schedule page. To see more
details, navigate to Operations » Schedule and click a test plan card.
• Switch between day, week, month, and year views on the Schedule page.
20
ni.com
Updates and Changes for SystemLink Enterprise 2024 and Earlier
• Download multiple files at once. 
• Apply a state to multiple systems at once. Navigate to Systems Management »
Systems. Select the systems and click More » Apply state.
November 2024
• Search, filter, and save custom views in Data Spaces. 
• View, add, and manage calibration data for assets. 
• Download a CSV reports for assets. Navigate to Systems Management » Assets and
click Download report.
• Forecast upcoming asset calibrations using the built-in calibration forecast
dashboard. Navigate to Systems Management » Assets. To launch the calibration 
forecast dashboard, click Calibration forecast.
• Improved query performance for data tables. 
• Added support for Kubernetes 1.29. 
• Added support for PostgreSQL 15.
October 2024
• Use the scheduling assistant to see what systems and DUTs are available and
schedule test plans without conflicts.
• Add comments with @ mention and rich text on work orders and test plans. 
• Configure resource profiles to maximize resource utilization for the Notebook
Execution Service. In systemlink-values.yaml, you can modify the low, 
medium, or high resource profiles.
• When viewing your data tables in a data space, you can now view your data in a
table as well as a chart.
September 2024
• Navigate to Operations » Schedule to view the test plans scheduled across all
systems in timeline view.
• Use the following new features when visualizing data tables in data spaces.
◦ Search for columns to plot from the axis selection grid. 
◦ Color traces by data table and by column metadata.
• Adjust how long the SystemLink Enterprise Alarm Service keeps your alarms. 
• Adjust how many alarms you can create in the SystemLink Enterprise Alarm
© National Instruments 21
Updates and Changes for SystemLink Enterprise 2024 and Earlier
Service.
• Learn about the performance metrics for the Dashboard Host Alarm Service. 
• Support for private certificate authorities.
◦ Connect to MongoDB and S3 compatible interfaces that use certificates signed
by a private authority.
◦ Call SystemLink APIs from Jupyter Notebook when the SystemLink API
endpoint is configured to use a certificate signed by a private authority.
August 2024
• Enable, delete, or disable multiple routines at once. Navigate to Analysis »
Routines and select the routines you want to modify.
• View and manage data tables across all test results. Navigate to Product Insights »
Data Tables and select the data tables you want to interact with.
• Learn about data limits for proxy servers and for ingress controllers. 
• Learn about the performance metrics for the SystemLink Alarm Service.
July 2024
• Align the x-axis of your data table plots to zero. 
• Decimate the data in your Data Spaces plots using Lossy, Max/Min, or Entry/Exit
modes.
• Filter and save a custom view of a test plans grid. 
• SystemLink Enterprise adds the workspace property to products. For products
already in your system, SystemLink Enterprise assigns a workspace using the 
following logic.
SystemLink Enterprise assigns the workspace 
associated with the first test results listed for 
the product.
The product has test results.
The product does not have test results. 
SystemLink Enterprise assigns the default 
workspace.
For new products, assign a workspace so you can control access
22
ni.com
Updates and Changes for SystemLink Enterprise 2024 and Earlier
June 2024
• Create alarms to notify you when an issue occurs in your system. 
• Delete one or more product specifications you no longer need. 
• Select one or more Test Results and send them to a Jupyter Notebook for analysis. 
• Select one or more product specifications and send them to a Jupyter Notebook
for analysis.
• Automatically copy files linked to a test plan template when you create a test plan
from the template.
• Filter the test plans grid by using test plan metadata.
May 2024
• Navigate SystemLink Enterprise faster with the intuitively organized Home page
and the navigation pane.
• Visualize data tables in a data space to gain insights into your time-series data. 
• Analyze test results with Jupyter Notebook. 
• Annotate steps with keywords from a data space. 
• Save custom column configurations for the product specifications grid. 
• Create and manage test plans under a product. 
• Define and apply custom states to a system.
April 2024
• Create test plans faster by using a test plan template. 
• Edit result keywords from a data space. You can also exclude results from a data
space using a keyword that the results have in common.
• Learn about the performance metrics for the SystemLink DataFrame service. 
• Create feeds and upload custom packages. 
• Replicate feeds from a remote URL. 
• Upload, download, and configure metadata for system state files. 
• Easily move third-party assets between test systems or unmanaged locations.
March 2024
• Use the Specification Management UI to maintain a central repository of
specifications that you can use to analyze your test results and measurements.
© National Instruments 23
Updates and Changes for SystemLink Enterprise 2024 and Earlier
• Extract Standard Test Data Format (STDF) files into SystemLink results, steps, and
measurements.
• Learn how SystemLink performs when extracting test data from Bench Data
Connector (BDC) files and STDF files.
• Duplicate existing routines so you can create similar routines faster. In the
SystemLink web application, navigate to Analysis » Routines. Select a routine and 
click Duplicate.
February 2024
• Use the SystemLink Enterprise Test Plans Module to create, view, and manage
work orders and test plans for the products you are testing.
• Use Specification Management APIs to maintain a central repository of
specifications. Use specifications to store test limits and test conditions.
• Create routines to automate an action when an event occurs. 
• Distribute Helm charts through the Docker registry to simplify your deployment. 
• Added support for Kubernetes 1.28.
January 2024
• Added support for SystemLink Client 2024 Q1. 
• Activate SystemLink Enterprise offline. 
• You can @ mention other users in comments on test results and data spaces. 
• Trigger test data extraction routines from the Product details page. 
• You can trend step data from the Results details page directly into a data space. 
• Monitor disk utilization for your JupyterHub user data. You can see the utilization
in the main status bar at the bottom of the window.
• Enable dark mode which tracks the settings for your device.
Related concepts:
• Managing Work Orders and Work Items 
• Specification Compliance 
• Data Limits for Proxy Servers and for Ingress Controllers 
• Private Certificate Authorities
Related tasks:
24
ni.com
Updates and Changes for SystemLink Enterprise 2024 and Earlier
## • Automating Actions with Routines 
• Creating a Test Plan 
• Annotating Test Results or Steps with Keywords from a Data Space 
• Analyzing Test Results with Jupyter Notebook 
• Visualizing Data Tables in a Data Space 
• Deleting Specifications 
• Generating Custom Alarms 
• Analyzing Specification Compliance with Jupyter Notebook 
• Creating a Workspace 
• Configuring Alarm Retention 
• Configuring Alarm Limits 
• Viewing Scheduled Test Plans 
• Scheduling a Test Plan 
• Configuring the Notebook Execution Service 
• Analyzing Parametric Data in a Data Space 
• Creating a Custom Script for Analyzing Parametric Data
Related reference:
• Data Extraction Performance for Standard Files 
• DataFrame Service Metrics 
• Alarm Service Metrics 
• Dashboard Host Service Metrics
2023
December 2023
• You can track the location history of your assets. 
• You can manage files associated with your assets. 
• You can enable software installation from ni.com or a remote URL by adding those
locations as feeds on your system.
• You can visualize parametric data in histograms in data spaces.
October 2023
• You can add comments to test results.
© National Instruments 25
Updates and Changes for SystemLink Enterprise 2024 and Earlier
• You can view the current and historical values of a tag in dashboards. 
• Data tables have improved reliability and scalability and can support thousands of
concurrent writers.
• You can connect to external MongoDB instances. 
• You can view all tracked assets on the Assets page. 
• You can change the version of a package installed on a managed system.
September 2023
• You can change the version of software installed on a system from the System
Details page.
• You can specify a part number as additional tracked metadata when adding new
assets to SystemLink.
August 2023
• Install software on a system from feeds that are already configured on the device.
In the SystemLink web application, select Systems Management » Systems. 
Double-click a system, open the Software tab, and click Install software.
• View detailed information about jobs that have executed on a system. In the
SystemLink web application, select Systems Management » Systems. Double-click 
a system, open the Jobs tab, select a job, and click View.
July 2023
• View detailed test step data under a test result. 
• Results and Products grids display a count of items that match a query. 
• Visualize parametric data with a single click from a test result or from the test
results grid.
• View box, violin, and histogram charts in the margins of a scatter chart in a data
space.
• Color traces in scatter charts by product, result, step, condition, and measurement
data.
• The Systems grid tag column supports autocomplete for tag paths. 
• Added the Tag Historian Service. 
• Copy a tag path using the context menu in the Tags grid on the System Details
page.
26
ni.com
Updates and Changes for SystemLink Enterprise 2024 and Earlier
• Delete tags in the Tags grid on the System Details page. 
• Notebook dropdowns group notebooks by workspace.
June 2023
• Track the location and status of assets on the Assets tab for your system. 
• Manually add assets to your system to track third-party devices and devices
without drivers.
• Edit and delete data spaces from the data spaces table and from an individual data
space.
• The PostgreSQL backend for the Test Insights Service is more resilient.
May 2023
• Added tags. Publish and view the current value of tags from your test systems.
Monitor the status of your test fleet with automatically published system health 
data on the System Details page.
April 2023
• Create data spaces to view parametric test data on a scatter chart. 
• The DataFrame Service uses streaming data deserialization. This allows you to use
larger batch sizes with more rows per write.
• The Dremio S3 automatically promotes missing data sets on query. You get
improved reliability in scenarios where a dataset is deleted at the same time it is 
queried. To uptake this change, delete all Dremio PVCs and restart all Dremio and 
DataFrame Service pods.
• You can show custom properties in the Files grid and create saved views. 
• You can filter the steps grid by step and measurement name. 
• The default pull policy for images in argo-workflows has changed. Instead of
always, the new default is IfNotPresent.
• The executions grid groups by status by default. 
• Schedule routines are enabled by default. 
• The feature flag
routineservice.featureToggle.publishScheduleEvent has been 
removed from the SystemLink Helm chart.
• The DataFrame Service has new limits intended to ensure availability of the
© National Instruments 27
Updates and Changes for SystemLink Enterprise 2024 and Earlier
service.
March 2023
• Export data tables to CSV. 
• Query product, results, and steps tables with the table query builder. 
• Added support for Kubernetes 1.23. 
• Added support for PostgreSQL 13 and 14. 
• Added telemetry metrics for the Test Monitor Service, Data Frame Service, and
Kafka service.
• Replaced oidc/user-info with /oidc/userinfo as the endpoint to view
claims for the current logged in user.
• Enabled Kafka UI for debugging and monitoring. 
• Increased the default memory provided to Kafka topic operator from 256 MB to
512 MB to increase the total number of tables the Data Frame Service can write to.
• Kafka S3 sink connectors are automatically deleted if a data table is marked
endOfData.
• Deleted Kafka S3 sink connectors are automatically reestablished if connectors are
manually deleted.
February 2023
• Added support for PostgreSQL 14.x. 
• Add, remove, and reorder columns in the Steps grid when viewing the details of a
test result.
January 2023
• Schedule a Jupyter notebook to run at a specific time or on a repeating schedule. 
• View detailed information about individual test steps for a test result. Refer to
Viewing Test Steps by Result.
• Access SystemLink navigation and user account settings when using the Jupyter
environment.
Related tasks:
• Viewing Test Steps by Result
28
ni.com
Updates and Changes for SystemLink Enterprise 2024 and Earlier
• Filtering Grids 
• Normalizing Incoming Data Automatically 
• Plotting Parametric Data in a Data Space 
• Viewing Test Results by Product 
• Collaborating on Test Results 
• Monitoring Data with Tags 
• Choosing a MongoDB Deployment 
• Configuring MongoDB Instances 
• Managing Your Assets
2022
December 2022
• The top level helm chart includes the License Service. Refer to the release notes for
details on the required configuration for this service.
• You can specify data table IDs as variables in dashboards. 
• You can customize, filter, save, and load views in the Products grid. 
• You can upload and view files associated with a product. 
• You can filter the Executions grid by date ranges and workspaces.
November 2022
• You can upload files up to 10GB through the web interface.
Related tasks:
• Using Data Tables as Dashboard Variables
© National Instruments 29
SystemLink Enterprise Theory of Operation
SystemLink Enterprise
SystemLink Enterprise  Theory of Operation 
Theory of Operation
SystemLink Enterprise implements a server-client architecture to transmit data over a 
connected network between your systems and server.
The architecture of SystemLink Enterprise enables central coordination and 
management of the following:
• Test and measurement systems 
• Assets 
• Software 
• Data
Refer to the following image to learn about the SystemLink Enterprise architecture.
SSO - Single
Sign On
Test Systems
Users
Identity Provider
Docker, Kubernetes
Auto-scaling & Service discovery
API Load Balancer
Web server
File
Role-based
Systems
Asset
Test
DataFrame
Analysis
Dash-
Ingestion
Access
Management
Management
Insights
Tables
and Report 
Generation
boards and
Control
Data
Table 4. SystemLink Enterprise Architecture
Component 
Description
Stores and verifies user identity so users log into the SystemLink 
Enterprise web application.
Identity provider
SystemLink requires you to supply an identity provider that supports the 
OpenID Connect protocol.
Users 
Access SystemLink Enterprise through an OpenID Connect identity 
provider.
30
ni.com
SystemLink Enterprise Theory of Operation
Component 
Description
Execute test applications. 
SystemLink Enterprise can help you manage your test systems in the 
following ways.
• Install software at scale. 
• Track connected assets. 
• Automatically ingest the data produce by the test systems.
Test systems
SystemLink Enterprise manages the authentication and authorization of 
test systems with role-base access control.
Web server 
Enforces log-in configuration and redirection, inactivity timeout, and 
session management.
API load balancer 
Allows for high performance network communication directly into the 
Kubernetes cluster hosting SystemLink Enterprise.
Provides strong isolation between different workspaces as well as 
privileges for systems, data, and analysis routines in SystemLink 
Enterprise.
Role-based access 
control
You can manage roles and workspace access through OpenID Connect 
user claims or direct assignment.
Systems management 
Allows you to connect a test system to SystemLink Enterprise securely, 
manage system configuration and settings, and remotely install software.
Allows you to track assets connected to test systems and calculate the 
utilization of those assets.
Asset management
SystemLink Enterprise retains asset data when you move an asset 
between systems. You can track asset utilization outside of the connected 
system or test application.
Ingests test steps and test results using a TestStand plug-in or API.
You can organize test results by product. You can search test result by 
querying test meta data. You can also create higher level test metrics and 
data visualizations using integrations with analysis routines and 
SystemLink dashboards.
Test Insights
File ingestion 
Allows you to store files on-premise or in the cloud and query the files 
without complex database syntax.
© National Instruments 31
SystemLink Enterprise Theory of Operation
Component 
Description
You can access files through an API. Integration with Routines and 
Jupyter Notebooks enables you to perform custom analysis of files 
immediately upon upload.
Enables the normalization of disparate data and file formats into a 
columnar data structure.
DataFrame tables
You can associate DataFrame tables with test results. Then, you can use 
DataFrame tables to visualize and to search data.
Enables interactive and automated analysis routines of test data through 
Jupyter Notebooks.
Analysis and report 
generation
The routines can produce KPIs and computer analytics in dashboards. 
The routines can also produce HTML reports and PDF reports.
Provides container orchestration, auto-scaling, and life cycle 
management for the various services, web applications, and the 
infrastructure that makes up SystemLink Enterprise.
Kubernetes
32
ni.com
SystemLink Enterprise Examples
SystemLink Enterprise
SystemLink Enterprise  Examples 
Examples
You can find .NET, Python, and Jupyter Notebook examples in the SystemLink 
Enterprise GitHub repository. Use these examples to learn about the product or 
accelerate your own application development.
SystemLink Enterprise examples are located in the 
systemlink-enterprise-examples GitHub repository.
Table 5. Common SystemLink Enterprise .NET examples
Example Name 
Description
This example demonstrates how to use the 
SystemLink Test Monitor API to create test 
results and steps.
Test Monitor Results Example: Create Results 
and Steps
This example demonstrates how to use the 
SystemLink Test Monitor API to delete test 
results.
Test Monitor Results Example: Delete Results
Table 6. Common SystemLink Enterprise Python Examples
Example Name 
Description
This example demonstrates how to use the 
SystemLink Test Monitor API to create test 
results and steps.
Test Monitor Results: Create Results and Steps
This example demonstrates how to use the 
SystemLink Test Monitor API to delete test 
results.
Test Monitor Results: Delete Results
Table 7. Common SystemLink Enterprise Script Analysis Examples
Example Name 
Description
This example demonstrates how to analyze 
parametric data in a data space and calculate 
statistics.
Data Space Analysis
Specification Analysis 
This example demonstrates how to use the Spec 
Service to query, analyze, and update
© National Instruments 33
SystemLink Enterprise Examples
Example Name 
Description
specifications with the latest properties.
Test Results Analysis 
This example demonstrates how to create a 
Number of Failures Pareto chart for test results.
This example demonstrates how to use the 
SystemLink APIs to perform data extraction and 
normalization on a file.
Simple ETL
Table 8. Other SystemLink Enterprise Examples
Example Name 
Description
Test Plan Operations 
This example demonstrates how to define a test 
plan template and a custom test plan workflow.
Dynamic Form Fields Configuration 
This example demonstrates how to define a 
Dynamic Form Fields configuration.
Related information:
• SystemLink Examples on GitHub 
• SystemLink Python API Reference
34
ni.com
Navigating SystemLink Enterprise
Navigating 
Navigating SystemLink Enterprise 
SystemLink Enterprise
Find useful links on the SystemLink Enterprise home page.
Use the navigation menu 
 to access all applications within SystemLink Enterprise.
Use the account menu 
 to change your language settings.
Click the links in the Home page to launch the following helpful resources.
• SystemLink Docs: Open the SystemLink Enterprise User Manual on ni.com. 
• SystemLink Client Download: Go to the download page for SystemLink Client on
ni.com.
• API Documentation: Open the SystemLink REST API documentation specific to
your instance of SystemLink Enterprise.
Viewing and Editing User Account Settings 
Viewing and Editing User Account Settings
Use the SystemLink web interface to complete tasks such as modifying the language 
settings, picking an application color theme, and viewing account information.
1. In the top-right corner, click 
Welcome, <User Name> » Account.
2. In the Edit account slide-out, achieve the following goals.
© National Instruments 35
![image](images/pdf_image_35_1.png)

Navigating SystemLink Enterprise
Goal 
Description
Click the Language drop-down and select from the following languages:
Note By default, the language selector matches the langauge 
of the browser.
◦ English—English language setting 
◦ Français—French language setting 
◦ Deutsch—German language setting 
◦ 日本語
日本語—Japanese language setting
Set the language
◦ 中文
中文—Chinese language setting
The chosen language determines the decimal separator type and the 
locale to use for dates.
Click the Theme drop-down and select from the following themes:
◦ Light—A theme with light background and UI elements and dark text 
◦ Dark—A theme with dark background and UI elements and light text 
◦ Device default—SystemLink matches the default theme of the
device or browser
Set the color theme
Note SystemLink remembers the theme preference across 
browsers. Your chosen theme applies wherever you log in.
View the following account information:
Note You cannot edit these properties. Your organization 
provides this information through an identity management 
system such as Microsoft Azure AD, Okta, or Google 
Workspace.
◦ First name—The first name of the user 
◦ Last name—The last name of the user 
◦ Username—The unique identifier SystemLink uses for your account 
◦ Email—The email address SystemLink sends notifications 
◦ Phone—The phone number of the user
View information 
on your user 
account
Note If any of the account information is incorrect, contact 
your server administrator or IT support team to request an
36
ni.com
Navigating SystemLink Enterprise
Goal 
Description
update.
3. Click OK.
Filtering Grids 
Filtering Grids
Query your grids to create filtered views that you can reuse and share.
1. In the SystemLink Enterprise web application, expand the navigation menu and
click the application that best matches your goal. 
◦ Systems Management » Systems 
◦ Operations » Work Items 
◦ Operations » Work Orders 
◦ Product Insights » Products 
◦ Product Insights » Test Results 
◦ Product Insights » Files 
◦ Analysis » Routines 
◦ Analysis » Executions
2. Click 
 and define the query you want to use to filter items in your grid.
a. Select the property you want to use to filter the results.
A property can be a name, model, model number, and more.
b. Select the operation for how the property must correspond to the value.
Depending on the property you select, your query can only perform certain 
operations. 
For example, if you want to query for locked systems, you can perform only the 
equals operation or the does not equal operation.
c. Specify the value of the property you want to use to filter the results.
For example, you want to see only systems that are connected and have NI as the 
vendor. To create the view, use the following query settings.
Property 
Operator 
Value
Vendor 
contains 
NI
Connection Status equals 
Connected
© National Instruments 37
Navigating SystemLink Enterprise
3. Optional: To filter your grid successfully, repeat the filtering step, as needed. 
4. Click OK. 
5. Click 
.
6. In the Configure grid slide-out, use the Column tab to add or remove columns from
your view. To organize your grid items by shared traits, use the Grouping tab . You 
can click and drag the items in these tabs to change the order of the items in your 
view.
7. To access the view on a recurring basis, click the drop-down next to 
 and select
Save. Saving preserves your column, grouping, and sorting options as well.
To share a view with a user in your organization, send the URL to the user. To share a 
view with a user in another organization, export the view from the Configure View 
slide-out and send the resulting JSON file. Users can import this JSON file using the 
Create View slide-out. 
Related tasks:
• Filtering and Sorting Test Results by Custom Properties
38
ni.com
SystemLink Enterprise Installation and Configuration
SystemLink Enterprise
SystemLink Enterprise  Installation and 
Installation and
Configuration 
Configuration
SystemLink Enterprise is configured using Helm values set in YAML files and installed 
using Helm commands.
Ensure that you are familiar with Kubernetes concepts and the use of Helm charts.
Related information:
• Kubernetes 
• Helm
Configuring 
Configuring SystemLink Enterprise 
SystemLink Enterprise
SystemLink Enterprise installation is configured using Helm values set in YAML files.
Ensure that your system meets the requirements.
Downloading the Configuration Templates 
Downloading the Configuration Templates
Download templates of the YAML files you will use to configure SystemLink Enterprise.
Your configuration is stored in values files that must be retained for the lifetime of your 
deployment. NI recommends storing these files in a source control repository. You can 
find templates for these files in the templates folder on GitHub. 
Download systemlink-values.yaml, systemlink-admin-values.yaml, 
and systemlink-secrets.yaml from the templates folder.
Note These files contain detailed comments. NI recommends reading all the 
comments to understand the configuration that will be applied with your 
application. In many cases, you can use the default values. Comments 
marked with <ATTENTION> require a value or some additional attention. 
Review all <ATTENTION> comments and delete them when you are done.
© National Instruments 39
SystemLink Enterprise Installation and Configuration
Note These files hold the secrets for your SystemLink Enterprise 
deployment and must be retained for the lifetime of your deployment. You 
must restrict access to these files to avoid compromising the security of the 
application.
Related information:
• SystemLink Enterprise Templates
Configuring SystemLink Repositories 
Configuring SystemLink Repositories
Configure the NI public Helm repository and mirror it on an internal server.
SystemLink Enterprise is distributed using Helm charts and Docker images. These 
resources are located in the following artifact repositories. All repositories are 
authenticated.
Alias 
Default URL 
Description
Contains Docker 
container images and 
Helm charts.
ni-docker 

artifactory/ni-docker
Complete the following steps to add the NI public Helm repository to your local Helm 
instance. Use the username and the access key you received when you were granted 
access to SystemLink Enterprise.
1. Open the command prompt and run the following command.
helm registry login downloads.artifacts.ni.com --username 
user --password key
2. You might want to install the Helm chart from your own artifact repository. In this
case, replace the default registry URL with the URL of your artifact repository. The 
names and hierarchy of these artifacts must match 
downloads.artifacts.ni.com.
3. To install from a Docker mirror on an internal server, complete the following steps.
a. Open systemlink-values.yaml and systemlink-admin-
values.yaml.
40
ni.com
SystemLink Enterprise Installation and Configuration
b. In both files, set global.imageRegistry to the address of your registry.
Note You might also need to configure an image pull secret.
NI recommends configuring each mirror as a pull-through proxy for 
downloads.artifacts.ni.com. When a resource hosted on the NI repository is 
requested from the mirror, the mirror automatically downloads and caches the 
resource. This approach minimizes maintenance of the mirror while still providing 
control over what resources can be accessed locally. Refer to the documentation for 
your repository software to learn more about setting up a proxy server.
To download the Helm charts to push to your mirror, run the following commands.
helm pull oci://downloads.artifacts.ni.com/ni-docker/ni/
helm-charts/systemlink --version version
helm pull oci://downloads.artifacts.ni.com/ni-docker/ni/
helm-charts/systemlinkadmin --version admin-version
Where
• version is the specific version of the SystemLink Enterprise to download. 
• admin-version is the specific version of the systemlinkadmin Helm chart
to download.
Related reference:
• Required Secrets
Configuring Web Access to 
Configuring Web Access to SystemLink Enterprise 
SystemLink Enterprise
SystemLink Enterprise requires multiple routable host names to enable access to the 
application.
1. Open systemlink-values.yaml. 
2. To configure access to the UI, set the first value in the global.hosts array to
your chosen hostname. The SystemLink UI is the primary access point for the
© National Instruments 41
SystemLink Enterprise Installation and Configuration
application.
3. To configure the hostname for programmatic access to the SystemLink API, modify
the global.apiHosts array. For example, if your UI hostname is 
systemlink.myorganization.org, you can use systemlink-
api.myorganization.org.
4. To configure SaltMaster TCP access, create a layer2 MetalLB address pool for Salt.
Note This pool must contain all IP addresses that will be used for Salt 
access.
5. Modify
saltmaster.serviceTCP.annotations.metallb.universe.tf/
address-pool with the name of your address pool.
Note SystemLink Enterprise uses Salt to manage test systems. Salt is 
infrastructure management software that communicates with test 
systems using a TCP-based protocol on TCP ports 4505 and 4506.
Related information:
• Cluster Ingress 
• MetalLB Address Pool 
• Salt Project Welcome Website 
• Layer 2 Configuration 
• Salt Communication
Configuring an Elasticsearch Instance 
Configuring an Elasticsearch Instance
Configure SystemLink Enterprise to access a remote Elasticsearch database to 
enhance scalability and performance.
You must follow these steps under the following conditions.
• You are upgrading from a SystemLink Enterprise version before 2025-07. 
• You want to improve your search performance.
Note This feature is currently only available for the FileIngestion service.
42
ni.com
SystemLink Enterprise Installation and Configuration
Related concepts:
• Components of a SystemLink Enterprise System
Related tasks:
• Configuring Advanced Search for Files 
• Updating SystemLink Enterprise
Related information:
• Elastic Cloud 
• Elasticsearch GitHub Guide 
• Elasticsearch Delete Indices Documentation
Choosing an Elasticsearch Deployment
SystemLink uses Elasticsearch to improve search performance. You can use an 
Elasticsearch instance in the same Kubernetes cluster as your SystemLink Enterprise 
installation or an external instance.
Use the following table to choose the Elasticsearch deployment that best suits your 
use case.
Deployment 
When to Use 
Details
You can run this instance on 
existing Kubernetes worker 
nodes or dedicated worker 
nodes using taints and 
tolerations.
• You need your database in
the same Kubernetes 
cluster as your SystemLink 
Enterprise installation.
• Your organization is
SystemLink Elasticsearch Helm 
chart
comfortable managing an 
Elasticsearch instance.
For more information and 
recommended resources, refer 
to Sizing Considerations 
when Deploying an 
Elasticsearch Instance.
• You want user
autoprovisioning and user 
dedicated configurations 
for SystemLink Enterprise.
© National Instruments 43
SystemLink Enterprise Installation and Configuration
Deployment 
When to Use 
Details
For more information and 
recommended resources, refer 
to Sizing Considerations 
when Deploying an 
Elasticsearch Instance.
You want to simplify database 
provisioning, operation, 
backup, and restore operations.
Elastic Cloud
Configuring the SystemLink Elasticsearch Helm Chart with Enabled 
Autoprovisioning
To configure Elasticsearch for the first time, you must provision the passwords.
1. Open the elasticsearch.yaml file. 
2. Set the sl-elasticsearch.usersProvisioning.enabled value to
True.
3. Open the elasticsearch-secrets.yaml file. 
4. Set the password for each index.
Service 
User 
Password
fileingestioncdc filescdc 
sl-
elasticsearch.secrets.filescdcPassword
5. Deploy Elasticsearch.
Configuring a Remote Elasticsearch Instance or the SystemLink 
Elasticsearch Helm Chart with Disabled Autoprovisioning
To configure Elasticsearch for the first time, you must provision the indexes.
1. Open the systemlink-secrets.yaml file. 
2. Set the password for each index.
Note Some services require privileges on multiple indexes. For example, 
if the files,files_* parameter is specified, the service requires
44
ni.com
SystemLink Enterprise Installation and Configuration
privileges for the following indexes:
◦ The files index. 
◦ All indexes that match the files_* pattern (where * is a
wildcard).
Service 
Database 
User 
Password
fileingestioncdc files,files_* filescdc fileingestioncdc.secrets.elasticse
3. Deploy Elasticsearch.
Sizing Considerations When Deploying an Elasticsearch Instance
Configure the Elasticsearch instances to handle the scale of data you have.
Resource requirements are based on service usage. Refer to the following table for 
tested configurations at a specified scale when configuring resources based on your 
expected usage.
Note These resource requirements increase as Elasticsearch usage 
increases.
Service 
Scale 
Nodes 
CPU 
RAM 
Persistence 
Primary 
shards
FileIngestion 25 million files 
2 
1 
4 GB 
50 GB 
2
FileIngestion 80 million files 
4 
1 
4 GB 
200 GB 
4
Based on your scale, select and apply that configuration.
1. Open the elasticsearch.yaml file. 
2. Set the sl-elasticsearch.elasticsearch.master.replicaCount
value to the listed nodes.
3. Set the sl-
elasticsearch.elasticsearch.master.resources.requests.cpu 
value to the listed CPU.
© National Instruments 45
SystemLink Enterprise Installation and Configuration
4. Set the sl-
elasticsearch.elasticsearch.master.resources.requests.memory 
value and the sl-
elasticsearch.elasticsearch.master.resources.limits.memory 
value to the listed RAM.
5. Set the sl-
elasticsearch.elasticsearch.master.persistence.size value to 
the listed persistence storage size.
6. Open the systemlink.yaml file. 
7. Set the
fileingestioncdc.job.connectors.sink.elasticsearch.index.primary
value to the listed number of shards.
Note The shards configuration only works when on the initial 
deployment. To change the configuration after the first deployment, you 
must manually delete the files index from Elasticsearch and redeploy the 
FileIngestionCDC application.
Configuring File Storage 
Configuring File Storage
Several SystemLink Enterprise services require a file storage provider.
The following list contains the supported providers:
• Amazon S3 Storage 
• Amazon S3 Compatible Storage 
• Azure Blob Storage
Note An Amazon S3 compatible file storage provider must implement 
the full Amazon S3 API. For more information, refer to the Amazon S3 API 
Reference. The Data Frame Service does not support the GCS Amazon S3 
interoperable XML API.
Amazon S3 storage and Azure Blob storage typically share the parameters in the 
following tables across multiple configurations. Sharing occurs through YAML anchor
46
ni.com
SystemLink Enterprise Installation and Configuration
syntax in the Helm values files. This syntax provides a convenient way to share a 
common configuration throughout your values files. You can override individual 
references to these values with custom values.
Amazon S3 and Amazon S3 Compatible Storage Providers
Note You can encrypt objects in Amazon S3 storage using either SSE-S3 or 
SSE-KMS with a bucket key. For more information, refer to Protecting 
Amazon S3 Data with Encryption.
Set the following configuration in your AWS/aws-supplemental-values.yaml 
Helm configuration file or OnPrem/storage-values.yaml Helm configuration 
file. For more information on deploying configurations to your environment, refer to 
Updating SystemLink Enterprise.
You can configure secret references in the AWS/aws-secrets.yaml file, the 
OnPrem/storage-secrete.yaml file, or directly on the cluster. For more 
information on managing the secrets that the configuration requires for file storage, 
refer to Required Secrets.
Table 9. Amazon S3 and Amazon S3 Compatible Storage Parameters
Parameters Before the 2025-07 Release 
Parameters After the 2025-07 Release
• dataframeservice.storage.ty
• fileingestion.storage.type 
• fileingestioncdc.highAvaila
• feedservice.storage.type 
• nbexecservice.storage.type
Not applicable
• dataframeservice.s3.port 
• fileingestion.s3.port 
• feedservice.s3.port 
• nbexecservice.s3.port
• dataframeservice.storage.s3
• fileingestion.storage.s3.po
• feedservice.storage.s3.port
• nbexecservice.storage.s3.po
© National Instruments 47
SystemLink Enterprise Installation and Configuration
Parameters Before the 2025-07 Release 
Parameters After the 2025-07 Release
• dataframeservice.storage.s3
• fileingestion.storage.s3.ho
• fileingestioncdc.highAvaila
• feedservice.storage.s3.host
• nbexecservice.storage.s3.ho
• dataframeservice.s3.host 
• fileingestion.s3.host 
• feedservice.s3.host 
• nbexecservice.s3.host
• dataframeservice.s3.schemeName 
• fileingestion.s3.scheme 
• feedservice.s3.scheme 
• nbexecservice.s3.scheme
• dataframeservice.storage.s3
• fileingestion.storage.s3.sc
• feedservice.storage.s3.sche
• nbexecservice.storage.s3.sc
• dataframeservice.storage.s3
• fileingestion.storage.s3.re
• fileingestioncdc.highAvaila
• feedservice.storage.s3.regi
• nbexecservice.storage.s3.re
• dataframeservice.s3.region 
• fileingestion.s3.region 
• feedservice.s3.region 
• nbexecservice.s3.region
• dataframeservice.sldremio.distStorage 
Unchanged
48
ni.com
SystemLink Enterprise Installation and Configuration
Parameters Before the 2025-07 Release 
Parameters After the 2025-07 Release
• dataframeservice.storage.s3
• fileingestion.storage.s3.se
• fileingestioncdc.highAvaila
• feedservice.storage.s3.secr
• nbexecservice.storage.s3.se
• dataframeservice.storage.s3.auth.secretName 
• fileingestion.storage.s3.secretName 
• feedservice.storage.s3.secretName 
• nbexecservice.storage.s3.secretName
Begining with the 2025-11 release, fileingestioncdc adds the following parameters.
Parameter 
Details
This value represents 
the port number of the 
storage provider 
service.
fileingestioncdc.highAvailability.storage.s3.port
This value represents 
the scheme of the 
storage provider 
service. This value is 
typically https.
fileingestioncdc.highAvailability.storage.s3.scheme
Connecting Services to S3 through IAM
Assign an IAM role to connect services to Amazon S3.
Your system must meet the following prerequisites to connect each service through 
IAM.
• Create an account for each service by setting the following Helm value:
serviceAccount: create: true.
Note Flink services do not require this Helm value. The Flink Operator 
manages the service account.
• Create an IAM policy with the following statement:
© National Instruments 49
SystemLink Enterprise Installation and Configuration
"Action": [ 
  "s3:PutObject", 
  "s3:ListBucket", 
  "s3:GetObject", 
  "s3:DeleteObject", 
  "s3:AbortMultipartUpload" 
], 
"Effect": "Allow", 
"Resource": [ 
  "<s3_bucket_ARN>/*", 
  "<s3_bucket_ARN>" 
]
Note The <s3_bucket_ARN> placeholder represents the Amazon 
Resource Name for the S3 bucket of the service.
• Create an IAM role that applies the new IAM policy.
Note Most IAM roles use the following naming convention: <release-
name>-<service-name>-role. For example, systemlink-
feedservice-role. Flink services do not follow this rule. Instead, IAM 
roles for Flink services share the same configuration as the Flink 
Operator. These roles use the following naming convention: <release-
name>-flink-role.
After meeting these prerequisites, update the Helm values file to include the following 
configurations.
Service 
Configuration
DataFrame Service 
This service does not currently support IAM.
feedservice: 
  storage: 
    s3: 
      authType: 
"AWS_WEB_IDENTITY_TOKEN"
Feed Service
feedservice:
50
ni.com
SystemLink Enterprise Installation and Configuration
Service 
Configuration
serviceAccount: 
    annotations: 
      eks.amazonaws.com/role-arn: 
"arn:aws:iam::<account-
id>:role/<release-name>-feedservice-
role"
fileingestion: 
  storage: 
    s3: 
      authType: 
"AWS_WEB_IDENTITY_TOKEN"
File Ingestion Service
fileingestion: 
  serviceAccount: 
    annotations: 
      eks.amazonaws.com/role-arn: 
"arn:aws:iam::<account-
id>:role/<release-name>-fileingestion-
role"
fileingestioncdc: 
  highAvailability: 
    storage: 
      s3: 
        authType: 
"AWS_WEB_IDENTITY_TOKEN"
File Ingestion CDC
flinkoperator: 
  flink-kubernetes-operator: 
    jobServiceAccount: 
      annotations: 
        eks.amazonaws.com/role-arn: 
"arn:aws:iam::<account-
id>:role/<release-name>-flink-role"
nbexecservice: 
  storage:
Notebook Execution Service
© National Instruments 51
SystemLink Enterprise Installation and Configuration
Service 
Configuration
s3: 
      authType: 
"AWS_WEB_IDENTITY_TOKEN"
nbexecservice: 
  serviceAccount: 
    annotations: 
      eks.amazonaws.com/role-arn: 
"arn:aws:iam::<account-
id>:role/<release-name>-executions-
role"
Azure Blob Storage Providers
Note For the Data Frame service storage account, you must disable blob 
soft delete and hierarchical namespace.
Set the following configuration in the Azure/azure-supplemental-
values.yaml Helm configuration file for Azure Blob Storage.
You can configure secret references in the Azure/azure-secrets.yaml file or 
directly on the cluster. For more information on deploying these configurations to your 
environment, refer to Updating SystemLink Enterprise.
Note The storage account for the Data Frame service must have blob soft 
delete and hierarchical namespace disabled.
Table 10. Azure Blob Storage Parameters
Parameters Starting with the 2025-07 Release 
Details
• dataframeservice.storage.type 
• fileingestion.storage.type 
• fileingestioncdc.highAvailability.storage.type 
• feedservice.storage.type
This value represent
of the service. Set th
52
ni.com
SystemLink Enterprise Installation and Configuration
Parameters Starting with the 2025-07 Release 
Details
• nbexecservice.storage.type
This value represent
Azure Blob storage w
name. For example,
value to blob.cor
or 
blob.core.usgo
• dataframeservice.storage.azure.blobApiHost 
• fileingestion.storage.azure.blobApiHost 
• fileingestioncdc.highAvailability.storage.azure.blobApiHost 
• feedservice.storage.azure.blobApiHost 
• nbexecservice.storage.azure.blobApiHost
If your storage does 
port, add the port to
host. For example, 
blob.core.wind
This value represent
port of the Azure Da
connect to without t
For example, you ca
dfs.core.windows.ne
• dataframeservice.storage.azure.dataLakeApiHost
If your storage does 
port, add the port to
host. For example: 
dfs.core.windo
• dataframeservice.storage.azure.accountName 
• fileingestion.storage.azure.accountName 
• fileingestioncdc.highAvailability.storage.azure.accountName 
• feedservice.storage.azure.accountName 
• nbexecservice.storage.azure.accountName
This value represent
account for your ser
recommends using 
accounts for differen
Limits and Cost Considerations for File Storage
To adjust limits and cost considerations for file storage services, refer to the following 
configurations.
© National Instruments 53
SystemLink Enterprise Installation and Configuration
Table 11. File Storage Considerations
Consideration 
Configuration
To clean up incomplete multipart uploads, configure your service. If you 
are using Amazon S3, configure the 
AbortIncompleteMultipartUpload value on your S3 buckets.
Reduce storage costs
Note Azure storage automatically deletes uncommitted 
blocks after seven days. For other S3 compatible providers, 
refer to the provider documentation.
Configure the fileingestion.rateLimits.upload value.
Adjust the number of 
files a single user can 
upload per second
By default, the value is 3 files per second per user. By load balancing 
across replicas, the effective rate is higher than the specified rate.
Adjust the maximum file 
size that users can 
upload
Configure the fileingestion.uploadLimitGB value.
By default, the value is 2 GB.
Adjust the number of 
concurrent requests that 
a single replica can serve 
for ingesting data
Configure the 
dataframeservice.rateLimits.ingestion.requestLimit 
value.
Related tasks:
• Updating SystemLink Enterprise
Related reference:
• Required Secrets
Related information:
• Amazon S3 API Reference 
• Protecting Amazon S3 Data with Encryption
54
ni.com
SystemLink Enterprise Installation and Configuration
• SystemLink values Helm template 
• SystemLink Azure supplemental values Helm template 
• SystemLink AWS supplemental values Helm template 
• SystemLink Secrets Helm Template 
• SystemLink Azure Secrets Helm Template 
• Configuring a Bucket Lifecycle Configuration to Delete Incomplete Multipart
Uploads
• Configuring a Bucket Lifecycle Configuration to Delete Incomplete Multipart
Uploads in GCS
• GCS Amazon S3 Interoperability API Reference 
• IAM permissions for XML requests 
• Soft Delete for Blobs 
• Azure Data Lake Storage Hierarchical Namespace
Required Permissions for File Storage 
Required Permissions for File Storage
Some services, such as Amazon S3 and Google Cloud Storage (GCS), require more 
permissive access to file storage.
Amazon S3
You can use the following list of Amazon S3 permissions to map the permissions 
required for your Amazon S3 compatible storage.
Table 12. Amazon S3 Permissions
Actions 
Resources
• s3:GetBucketLocation 
• s3:ListAllMyBuckets 
arn:aws:s3:::*
• <file-ingestion-service-arn> 
• <file-ingestion-service-arn>/* 
• <dataframe-service-bucket-arn> 
• <dataframe-service-bucket-arn>/* 
• <dataframe-service-cache-bucket-
• s3:ListBucket 
• s3:PutObject 
• s3:GetObject
arn>
© National Instruments 55
SystemLink Enterprise Installation and Configuration
Actions 
Resources
• <dataframe-service-cache-bucket-
arn>/*
• <notebook-execution-service-arn> 
• <notebook-execution-service-
arn>/*
• <feed-service-arn> 
• <feed-service-arn>/*
• <dataframe-service-bucket-arn> 
• <dataframe-service-bucket-arn>/* 
• <dataframe-service-cache-bucket-
arn>
• <dataframe-service-cache-bucket-
s3:DeleteObject
arn>/*
• <notebook-execution-service-arn> 
• <notebook-execution-service-
arn>/*
• <feed-service-arn> 
• <feed-service-arn>/*
• <dataframe-service-bucket-arn> 
• <dataframe-service-bucket-arn>/* 
• <dataframe-service-cache-bucket-
arn>
• s3:ListMultipartUploadParts 
• s3:ListBucketMultipartUploads 
• s3:AbortMultipartUpload
• <dataframe-service-cache-bucket-
arn>/*
• <notebook-execution-service-arn> 
• <notebook-execution-service-
arn>/*
• <feed-service-arn> 
• <feed-service-arn>/*
SSE-KMS encryption requires a KMS key policy that grants access to the SystemLink 
service. Use the following list of AWS permissions and roles to map the KMS key policy 
permissions.
56
ni.com
SystemLink Enterprise Installation and Configuration
Table 13. SSE-KMS Encryption Principals
AWS Principal 
Actions 
Resource
• <dataframe-service-
user-arn>
• <notebook-
execution-service-
user-or-role-arn>
• kms:GenerateDataKey 
• kms:Decrypt 
<kms-key-arn>
• <feed-service-user-
or-role-arn>
• <file-ingestion-
service-user-or-
role-arn>
<account-root-arn> 
kms:* 
<kms-key-arn>
Azure Blob Storage
The built-in Storage Blob Data Contributor role contains all the necessary permissions 
for DataFrame Service, Feed Service, File Ingestion Service, and Notebook Execution 
Service.
The following table outlines the necessary permissions for various resources.
Note
The Feed Service containers require fine-grained access control.
Table 14. Azure Blob Storage Permissions
Permissions 
Resources
Microsoft.Storage/
storageAccounts/blobServices/
containers/readMicrosoft.Storage/
storageAccounts/blobServices/
containers/write
The containers for the DataFrame Service, Feed 
Service, and the Notebook Execution Service.
© National Instruments 57
SystemLink Enterprise Installation and Configuration
Permissions 
Resources
• Microsoft.Storage/
storageAccounts/blobServices/
containers/blobs/add/action
• Microsoft.Storage/
The containers and objects for the DataFrame 
Service, File Ingestion Service, Feed Service, and 
the Notebook Execution Service.
storageAccounts/blobServices/
containers/blobs/read
• Microsoft.Storage/
storageAccounts/blobServices/
containers/blobs/write
The containers and objects of the DataFrame 
Service, Feed Service, and the Notebook 
Execution Service.
Microsoft.Storage/
storageAccounts/blobServices/
containers/blobs/delete
Google Cloud Storage Amazon S3 Interoperable XML API
The following table outlines the necessary permissions for various resources.
Note
The Feed Service buckets require fine-grained access control. The Data 
Frame Service does not support the GCS Amazon S3 interoperable XML API.
Table 15. Google Cloud Storage Amazon S3 Permissions
Permissions 
Resources
• storage.buckets.get 
• storage.buckets.list
The buckets for the File Ingestion Service, the Feed 
Service, and the Notebook Execution Service.
• storage.objects.list 
• storage.objects.create 
• storage.objects.get
The buckets and objects for the File Ingestion Service, the 
Feed Service, and the Notebook Execution Service.
58
ni.com
SystemLink Enterprise Installation and Configuration
Permissions 
Resources
storage.objects.delete 
The buckets and objects of the Feed Service and the 
Notebook Execution Service.
Configuring OpenID Connect Client Access 
Configuring OpenID Connect Client Access
Configure the application to use your authentication provider. SystemLink Enterprise 
uses the OpenID Connect protocol to authenticate users from an external 
authentication provider.
Before you begin, register SystemLink Enterprise as a client with your authentication 
provider. Refer to the documentation for your authentication provider for the specific 
registration process. Use the UI hostname of the application for the registration. 
After registration, you should have a client id and a client secret value for 
your application. You might also have a JSON web key set (JWKS) depending on your 
provider. You need these plus the URL of your authentication provider to configure 
SystemLink Enterprise.
1. Open systemlink-values.yaml. 
2. Set webserver.oidc.issuer to the URL of your authentication provider. Use
the following URL to configure the login redirect for your provider. 
[protocol]://[ui-hostname]/oidc/callback
3. Set the following parameters to the values you received during registration.
◦ webserver.secrets.oidc.clientId 
◦ webserver.secrets.oidc.clientSecret 
◦ webserver.secrets.oidc.jwks
Note If you are not using Helm to manage secrets, you must configure 
the OpenID Connect secret manually.
4. Optional: Configure the webserver.oidc.scope value to select the OpenID
Connect scopes that SystemLink Enterprise will request. By default, SystemLink 
Enterprise requests the openid, email, and profile scopes. The openid 
scope is required. The profile and email scopes are used to populate user 
details in the UI. Other scopes might be useful when assigning user roles in the
© National Instruments 59
SystemLink Enterprise Installation and Configuration
application. Consult the documentation for your authentication provider to see 
what scopes are available.
Note Include the offline_access scope to enable users to view 
logged user claims at 
user-info. You can use this to ensure that the claim you want to use 
when setting up an OIDC Claim mapping is available to SystemLink.
5. Ensure that the authentication provider returns the following minimum claims
with each user's identity token. 
◦ email 
◦ given_name 
◦ family_name
6. Optional: Configure the webserver.oidc.userIDClaim value. This value is
the OpenID Connect claim that SystemLink Enterprise uses to identify a user. By 
default, SystemLink Enterprise uses the email address of the user.
Note If you change this value once the product is in use, all user 
permissions will be lost.
7. Optional: Configure the OpenID Connect claim that SystemLink Enterprise will use
as the user name for a given user. By default, this is the name property. This setting 
only affects how users are displayed in the UI.
8. Optional: The cluster might require a proxy server to access your OpenID Connect
authentication provider. In this case, set webserver.proxy.authority to 
the hostname and port of the proxy server.
9. Optional: If the proxy server requires credentials, uncomment
webserver.proxy.secretname.
10. Optional: In systemlink-secrets.yaml, configure
webserver.secrets.proxy.username and 
webserver.secrets.proxy.password or manually deploy these secrets.
Related concepts:
• Components of a SystemLink Enterprise System
Related reference:
60
ni.com
