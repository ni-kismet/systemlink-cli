using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Threading.Tasks;

namespace NationalInstruments.CommandLine.WorkflowCLI.Models
{
    /// <summary>
    /// An enumeration of test plan state.
    /// </summary>
    public enum TestPlanState
    {
        /// <summary>
        /// Default for new test plans.
        /// </summary>
        New,

        /// <summary>
        /// Requestor has specified the details for test plan.
        /// </summary>
        Defined,

        /// <summary>
        /// Test plan has been reviewed and is ready to be scheduled.
        /// </summary>
        Reviewed,

        /// <summary>
        /// Test plan has been scheduled.
        /// </summary>
        Scheduled,

        /// <summary>
        ///  Test plan is in progress.
        /// </summary>
        InProgress,

        /// <summary>
        /// Test plan is pending for approval.
        /// </summary>
        PendingApproval,

        /// <summary>
        ///  Test plan has been closed.
        /// </summary>
        Closed,

        /// <summary>
        /// Test plan has been canceled.
        /// </summary>
        Canceled,
    }
}
