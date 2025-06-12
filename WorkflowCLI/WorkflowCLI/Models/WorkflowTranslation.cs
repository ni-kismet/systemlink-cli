using System.ComponentModel.DataAnnotations;

namespace NationalInstruments.CommandLine.WorkflowCLI.Models
{
    /// <summary>
    /// Defines localized translations of text used within a workflow
    /// </summary>
    public class WorkflowTranslation
    {
        /// <summary>
        /// The 2-letter locale ID associated with the translation.
        /// </summary>
        /// <example>fr</example>
        [Required]
        [StringLength(2, MinimumLength = 2)]
        required public string LocaleId { get; set; }

        /// <summary>
        /// The translated display text.
        /// </summary>
        /// <example>Déployer le test</example>
        [Required]
        [StringLength(128, MinimumLength = 1)]
        required public string DisplayText { get; set; }
    }
}
