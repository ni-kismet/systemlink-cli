# Managing Work Orders

Create, view, and schedule work orders.

Exercises

- Exercise 7-1 Create and Schedule Test Plans

## Exercise 7-1: Create and Schedule Test Plans

### Goal

Create a test plan (work item) for a product, schedule the test plan on a system with a fixture and a device under test (DUT), and review scheduled tests in calendar views. 

### Scenario

The R&D team has submitted a work order called "Battery Validation – Model ABC" requesting thermal testing on a new battery pack design. You will create a test plan for this work order, schedule it on a test system, and review the schedule.

- Create a test plan (work item).
- Manage schedules across all systems or for a specific system, product, or DUT.
- Adjust scheduled test plans.

### Implementation

#### Create a Test Plan from a Work Order

1. Navigate to **Operations > Work Orders**.
2. Open **Battery Validation – Model ABC**.
3. Select the **Work Items** tab, then select **Create test plan**.
4. In **Product family**, select **Battery Packs**.
5. In **Product**, select **Model ABC** and click **Next**.

**Note**

When you select a product family, the Product list updates to show only products in that family. If you skip Product family, SystemLink updates the Product family selection based on the chosen product.

6. Select **Blank Test Plan** and click **Next**.
7. Configure the test plan:
   1. In the **Name** field, type **Thermal Cycle Test**.
   2. In **Assigned to**, select your username.
   3. Select the **Workspace** for the test plan (for example, **Default**).
   4. In **DUT**, select **BAT-DUT-C01**.
   5. In **Description**, type **Temperature cycling sequence for battery pack validation**.
8. Select **Create**. Confirm the test plan opens in the details page.

#### Schedule the Test Plan in Scheduling Assistant

1. From the **Thermal Cycle Test** details page, open the **⋯** menu and select **Open in the scheduling assistant**.
2. In the left pane, select **Chamber B** as the system and select **Slot_01** as the fixture.

**Note**

Shading in the schedule indicates time periods already allocated to other tests for the selected system.

3. Scroll down to the DUT section, and select **BAT-DUT-C01**.
4. In the **Schedule your work item here** row, click and drag the test plan to a time slot (for example, tomorrow morning at 9:00 AM).
5. Click **Save**.

#### Verify Fixture Allocation in the Work Items Table

1. Return to **Operations > Work Items**.
2. Review the fixture assignment for **Thermal Cycle Test**. Confirm it shows **Slot_01**.

**Note**

The Fixture column may be hidden by default. If needed, click the **Configure** button, and in the Configure grid pane, add the **Fixtures** column.

3. Use the summary tiles at the top of the page to filter work items and confirm the scheduled test plan remains listed. 

#### Review Test Plans for a Specific Product

1. Navigate to **Product Insights > Products**.
2. Select **Model ABC**.
3. Go to the **Work Items** tab to view test plans created for that product or DUT. Confirm **Thermal Cycle Test** appears.

#### Adjust a Scheduled Test Plan From the DUT

1. Navigate to **Systems Management > Assets**.
2. Select **BAT-DUT-C01**.
3. Select the **Work Items** tab.
4. Select the checkbox next to **Thermal Cycle Test**, and from the **Schedule** drop-down menu, select **Open in the scheduling assistant**.
5. In the left pane, select **Chamber B** as the system.
6. Scroll down to the DUT section, and select **BAT-DUT-C01**.
7. In the **Schedule your work item here** row, click and drag the test plan to a different time slot (for example, move it one hour later).
8. Click **Save**.

#### View Scheduled Tests Across Systems

1. Navigate to **Operations > Schedule**.
2. Review scheduled test plans for all systems.
3. To narrow the schedule view, select **Configure query** and apply filters (for example, filter by system **Chamber B**).
4. Open the **View** drop-down, select **Create view**, enter **Battery Test Schedule** as the name, then click **Create** to save the filtered schedule as a custom view.

**Tip**

To show upcoming schedule conflicts in the selected timeline, open **Settings** and turn on **Show upcoming schedule conflicts in the selected timeline**.

#### View and Adjust Schedules For a Specific System

1. Navigate to **Systems Management > Systems**.
2. Select **Chamber B**, and then select the **Schedule** tab.
3. Use the calendar controls as needed:
   1. Move between months using **Next month** and **Previous month**.
   2. Change the calendar view (Days, Week, Month, Year).
   3. Jump to a specific date using the calendar date selector, or select **Today**.
   4. Select **Thermal Cycle Test** on the calendar to open details.
   5. To reschedule, drag the test plan to a new time slot.

#### Unguided/Assess Your Skills

1. Create a test plan from a work order. Navigate to **Operations > Work Orders**, open **Battery Validation – Model ABC**, select the **Work Items** tab, and then select **Create test plan**.
2. Create a test plan from a DUT. Navigate to **Systems Management > Assets**, open **BAT-DUT-C01**, select the **Work Items** tab, and then select **Create test plan**.

**End of Exercise 7-1**
