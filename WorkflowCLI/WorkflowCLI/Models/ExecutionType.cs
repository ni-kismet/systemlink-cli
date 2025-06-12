using System;
namespace NationalInstruments.CommandLine.WorkflowCLI.Models
{
    /// <summary>
    /// The allowed execution types for a test plan.
    /// </summary>
    public enum ExecutionType
    {
        /// <summary>
        /// Will not trigger an execution, but will transition the test plan state in accordance with the action.
        /// </summary>
        Manual,

        /// <summary>
        /// Will trigger a notebook execution.
        /// </summary>
        Notebook,

        /// <summary>
        /// Will trigger a Systems Management job.
        /// </summary>
        Job,

        /// <summary>
        /// Special execution type that is managed by the Schedule API.
        /// </summary>
        Schedule,

        /// <summary>
        /// Special execution type that is managed by the Schedule API.
        /// </summary>
        Unschedule,

        /// <summary>
        /// Will not trigger an execution or transition the test plan state. Should not show up in the UI.
        /// </summary>
        None
    }
}
