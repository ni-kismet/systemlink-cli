using System.Diagnostics;

namespace NationalInstruments.CommandLine.WorkflowCLI.Utilities
{
    public static class MermaidCLI
    {
        public static void GenerateImage(string mermaidCode, string outputFilePath)
        {
            Process process = StartMermaidCLI(outputFilePath);
            WriteToStandardIn(mermaidCode, process);
            string error = WaitForExit(process);
            HandleResult(outputFilePath, process, error);
        }

        public static void OpenImage(string filePath)
        {
            Process.Start(new ProcessStartInfo
            {
                FileName = filePath,
                UseShellExecute = true // Required to open with default app
            });
        }

        private static void HandleResult(string outputFilePath, Process process, string error)
        {
            if (process.ExitCode != 0)
            {
                Console.WriteLine("Mermaid CLI error:");
                Console.WriteLine(error);
            }
            else
            {
                Console.WriteLine($"SVG diagram written to \"{outputFilePath}\"");
            }
        }

        private static string WaitForExit(Process process)
        {
            string error = process.StandardError.ReadToEnd();
            process.WaitForExit();
            return error;
        }

        private static void WriteToStandardIn(string mermaidCode, Process process)
        {
            using (var writer = process.StandardInput)
            {
                writer.Write(mermaidCode);
            }
        }

        private static Process StartMermaidCLI(string outputFilePath)
        {
            var process = new Process
            {
                StartInfo = new ProcessStartInfo
                {
                    FileName = "mmdc.cmd",
                    Arguments = $"-i - -o \"{outputFilePath}\"",
                    RedirectStandardInput = true,
                    RedirectStandardOutput = false,
                    RedirectStandardError = true,
                    UseShellExecute = false,
                    CreateNoWindow = true
                }
            };
            process.Start();
            return process;
        }
    }
}
