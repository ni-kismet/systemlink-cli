namespace NationalInstruments.CommandLine.WorkflowCLI.Utilities
{
    public static class FileOperations
    {
        public static string ReadAll(string filename)
        {
            if (string.IsNullOrEmpty(filename))
            {
                throw new ArgumentException("Filename cannot be null or empty.", nameof(filename));
            }
            try
            {
                return File.ReadAllText(filename);
            }
            catch (Exception ex)
            {
                Console.WriteLine($"Error reading file {filename}: {ex.Message}");
                return string.Empty;
            }
        }
    }
}
