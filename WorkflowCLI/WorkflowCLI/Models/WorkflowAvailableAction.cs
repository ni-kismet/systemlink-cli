using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;

namespace NationalInstruments.CommandLine.WorkflowCLI.Models
{
    /// <summary>
    /// Defines an action that is available for a state within a workflow.
    /// </summary>
    public class WorkflowAvailableAction
    {
        /// <summary>
        /// The name of the action within the workflow that is available
        /// to be executed.
        /// </summary>
        /// <example>Deploy</example>
        [Required]
        required public string Action { get; set; }

        /// <summary>
        /// The state that the test plan will enter when the action is executed.
        /// </summary>
        /// <example>IN_PROGRESS</example>
        [Required]
        required public TestPlanState NextState { get; set; }

        /// <summary>
        /// The substate that the test plan will enter when the action is executed.
        /// </summary>
        /// <example>Deploying</example>
        [Required]
        required public string NextSubstate { get; set; }

        /// <summary>
        /// Whether or not the action should be shown in the UI.
        /// </summary>
        [DefaultValue(true)]
        public bool ShowInUI { get; set; } = true;
    }
}
