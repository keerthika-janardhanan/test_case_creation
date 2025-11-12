import { Box, Button, Checkbox, FormControl, FormLabel, Heading, Input, Select, Stack, Text, Textarea, useToast } from "@chakra-ui/react";
import { useState } from "react";
import { generateManualTable } from "../api/manual";
import { updateTestManager } from "../api/config";
import { useSessionStore } from "../state/session";
import { uploadFile } from "../api/files";

export function ManualTestsPage() {
  const toast = useToast();
  const { authToken } = useSessionStore();
  const [story, setStory] = useState("");
  const [coverage, setCoverage] = useState<"grouped" | "full">("full");
  const [includeUnlabeled, setIncludeUnlabeled] = useState(true);
  const [includeLogin, setIncludeLogin] = useState(false);
  const [markdown, setMarkdown] = useState("");

  const [datasheet, setDatasheet] = useState("");
  const [referenceId, setReferenceId] = useState("");
  const [idName, setIdName] = useState("");
  const [uploading, setUploading] = useState(false);
  const [uploadPath, setUploadPath] = useState("");

  const gen = async () => {
    try {
      const md = await generateManualTable({ story, coverage, includeUnlabeled, includeLogin });
      setMarkdown(md);
    } catch (err: any) {
      toast({ status: "error", title: "Generation failed", description: String(err?.message || err) });
    }
  };

  const updateConfig = async () => {
    try {
      const res = await updateTestManager({ scenario: story, datasheet, referenceId, idName }, authToken);
      toast({ status: "success", title: `Test manager ${res.mode}`, description: res.path });
    } catch (err: any) {
      toast({ status: "error", title: "Config update failed", description: String(err?.message || err) });
    }
  };

  const uploadAndUpdate = async (file: File | null) => {
    if (!file) return;
    if (!story.trim()) {
      toast({ status: "warning", title: "Story required", description: "Enter a story first." });
      return;
    }
    setUploading(true);
    try {
      const saved = await uploadFile(file, "framework-data", authToken);
      setUploadPath(saved);
      const filename = saved.split("/").pop() || saved;
      const res = await updateTestManager({ scenario: story, datasheet: filename, referenceId, idName }, authToken);
      setDatasheet(filename);
      toast({ status: "success", title: `Uploaded & ${res.mode}`, description: filename });
    } catch (err: any) {
      toast({ status: "error", title: "Upload+Update failed", description: String(err?.message || err) });
    } finally {
      setUploading(false);
    }
  };

  return (
    <Stack spacing={6}>
      <Heading size="lg">Manual Test Assets</Heading>
      <Box bg="white" borderRadius="lg" p={6} boxShadow="sm">
        <Stack spacing={4}>
          <FormControl>
            <FormLabel>Story</FormLabel>
            <Input value={story} onChange={(e) => setStory(e.target.value)} placeholder="Create Supplier" />
          </FormControl>
          <FormControl>
            <FormLabel>Coverage</FormLabel>
            <Select value={coverage} onChange={(e) => setCoverage(e.target.value as any)}>
              <option value="grouped">grouped</option>
              <option value="full">full</option>
            </Select>
          </FormControl>
          <Checkbox isChecked={includeUnlabeled} onChange={(e) => setIncludeUnlabeled(e.target.checked)}>Include unlabeled elements</Checkbox>
          <Checkbox isChecked={includeLogin} onChange={(e) => setIncludeLogin(e.target.checked)}>Include login injection</Checkbox>
          <Button onClick={gen} colorScheme="blue">Generate Manual Table</Button>
          <Textarea value={markdown} onChange={(e) => setMarkdown(e.target.value)} rows={10} placeholder="Markdown output" />
        </Stack>
      </Box>
      <Box bg="white" borderRadius="lg" p={6} boxShadow="sm">
        <Heading size="md" mb={4}>Update Test Manager</Heading>
        <Stack spacing={4}>
          <FormControl>
            <FormLabel>Datasheet</FormLabel>
            <Input value={datasheet} onChange={(e) => setDatasheet(e.target.value)} placeholder="CreateSupplierData.xlsx" />
          </FormControl>
          <FormControl>
            <FormLabel>Reference ID</FormLabel>
            <Input value={referenceId} onChange={(e) => setReferenceId(e.target.value)} placeholder="CreateSupplier001" />
          </FormControl>
          <FormControl>
            <FormLabel>ID Column Name</FormLabel>
            <Input value={idName} onChange={(e) => setIdName(e.target.value)} placeholder="CreateSupplierID" />
          </FormControl>
          <Button onClick={updateConfig}>Update</Button>
          <FormControl>
            <FormLabel>Quick Action: Upload Datasheet & Update</FormLabel>
            <Input type="file" onChange={(e) => uploadAndUpdate(e.target.files?.[0] ?? null)} isDisabled={uploading} />
            {uploadPath && <Text mt={2} color="gray.600">Last uploaded: {uploadPath}</Text>}
          </FormControl>
        </Stack>
      </Box>
    </Stack>
  );
}

