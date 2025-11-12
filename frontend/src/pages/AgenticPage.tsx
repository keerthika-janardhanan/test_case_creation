// Clean rebuilt AgenticPage component with inline datasheet mapping and updateInfo display.
import { useEffect, useRef, useState } from "react";
import { Badge, Box, Button, Code, FormControl, FormLabel, Heading, HStack, Input, Progress, Select, SimpleGrid, Stack, Table, Thead, Tbody, Tr, Th, Td, Text, Textarea, useToast } from "@chakra-ui/react";
import { previewAgentic, previewAgenticStream, payloadAgenticStream, generatePayload, persistFiles, pushChanges, keywordInspect, trialRunAgenticStream, trialRunExisting, uploadDatasheet, listDatasheets } from "../api/agentic";
import { updateTestManager, listTestManager } from "../api/config";
import type { TestManagerRow } from "../api/config";
import { useSessionStore } from "../state/session";

export function AgenticPage() {
  const toast = useToast();
  const { authToken, frameworkRepoPath, frameworkBranch, frameworkCommitMessage, setFrameworkRepoPath, setFrameworkBranch, setFrameworkCommitMessage } = useSessionStore();
  const [scenario, setScenario] = useState("");
  const [preview, setPreview] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [payloadSummary, setPayloadSummary] = useState<{ locators: number; pages: number; tests: number } | null>(null);
  const [payloadFiles, setPayloadFiles] = useState<{ path: string; content: string }[] | null>(null);
  const [phase, setPhase] = useState("");
  const [trialLogs, setTrialLogs] = useState("");
  const [trialSuccess, setTrialSuccess] = useState<boolean | null>(null);
  const [headedMode, setHeadedMode] = useState(true);
  // Mapping fields
  const [datasheetName, setDatasheetName] = useState("");
  const [referenceId, setReferenceId] = useState("");
  const [idName, setIdName] = useState("");
  // Test Manager ID/Description selection
  const [testCaseId, setTestCaseId] = useState("");
  const [testCaseDescription, setTestCaseDescription] = useState("");
  const [testManagerRows, setTestManagerRows] = useState<TestManagerRow[]>([]);
  const [loadingTestManager, setLoadingTestManager] = useState(false);
  // Datasheet file list (existing) and upload state
  const [availableSheets, setAvailableSheets] = useState<string[]>([]);
  const [loadingSheets, setLoadingSheets] = useState(false);
  const [uploading, setUploading] = useState(false);
  // Execute toggle
  const [executeValue, setExecuteValue] = useState<string>("Yes");
  // Asset search
  const [existingAssets, setExistingAssets] = useState<{ path: string; snippet: string; isTest: boolean; relevance?: number }[]>([]);
  const [selectedAssetPath, setSelectedAssetPath] = useState("");
  const [inspectLoading, setInspectLoading] = useState(false);
  const [inspectStatus, setInspectStatus] = useState("");
  const [inspectMessages, setInspectMessages] = useState<string[]>([]);
  const [refinedSteps, setRefinedSteps] = useState<any[]>([]);
  const abortRef = useRef<AbortController | null>(null);
  const debounceRef = useRef<number | undefined>(undefined);
  const canSearch = !!frameworkRepoPath?.trim();

  const runKeywordInspect = async (kw: string) => {
    if (!canSearch || !kw.trim()) return;
    setInspectLoading(true);
    try {
      const res = await keywordInspect(kw.trim(), frameworkRepoPath.trim(), frameworkBranch || undefined, 5);
      setExistingAssets(res.existingAssets || []);
      setRefinedSteps(res.refinedRecorderFlow?.steps || []);
      setInspectStatus(res.status);
      setInspectMessages(res.messages || []);
      const pick = (res.existingAssets || []).find(a => a.isTest) || (res.existingAssets || [])[0];
      setSelectedAssetPath(pick?.path || "");
    } catch (err: any) {
      setExistingAssets([]); setRefinedSteps([]); setInspectStatus("error"); setInspectMessages([String(err?.message || err)]);
    } finally { setInspectLoading(false); }
  };

  // Load existing datasheets from backend data/ directory
  useEffect(() => {
    const scan = async () => {
      if (!frameworkRepoPath?.trim()) { setAvailableSheets([]); return; }
      try {
        setLoadingSheets(true);
        const files = await listDatasheets(frameworkRepoPath || undefined);
        const names = (files || []).map((f: string) => f.split('/').pop() || f).filter(Boolean);
        setAvailableSheets(names.filter((n: string) => n.toLowerCase().endsWith('.xlsx') || n.toLowerCase().endsWith('.xls')));
      } catch { setAvailableSheets([]); } finally { setLoadingSheets(false); }
    };
    scan();
  }, [frameworkRepoPath]);

  // Load Test Manager rows for dropdown when repo path changes
  useEffect(() => {
    const loadTM = async () => {
      if (!frameworkRepoPath?.trim()) { setTestManagerRows([]); return; }
      setLoadingTestManager(true);
      try {
        const rows = await listTestManager(frameworkRepoPath.trim());
        setTestManagerRows(rows);
      } catch {
        setTestManagerRows([]);
      } finally {
        setLoadingTestManager(false);
      }
    };
    loadTM();
  }, [frameworkRepoPath]);

  // When user selects a TestCaseID from dropdown, auto-fill description (editable)
  useEffect(() => {
    if (!testCaseId) return;
    const row = testManagerRows.find(r => r.TestCaseID === testCaseId);
    if (row) {
      setTestCaseDescription(row.TestCaseDescription || "");
    }
  }, [testCaseId, testManagerRows]);

  const handleDatasheetUpload = async (file: File | null) => {
    if (!file) return;
    if (!scenario.trim()) { toast({ status: 'warning', title: 'Enter scenario before upload' }); return; }
    setUploading(true);
    try {
      const res = await uploadDatasheet(file, scenario, frameworkRepoPath || undefined, authToken);
      setDatasheetName(res.filename);
      toast({ status: 'success', title: 'Datasheet uploaded', description: res.filename });
      setAvailableSheets(prev => Array.from(new Set([res.filename, ...prev])));
    } catch (err:any) {
      toast({ status: 'error', title: 'Upload failed', description: String(err?.message || err) });
    } finally { setUploading(false); }
  };

  const onScenarioChange = (val: string) => {
    setScenario(val);
    if (!canSearch) return;
    if (debounceRef.current) window.clearTimeout(debounceRef.current);
    debounceRef.current = window.setTimeout(() => runKeywordInspect(val), 500);
  };

  const handlePreview = async () => {
    if (!scenario.trim()) { toast({ status: "warning", title: "Enter scenario keyword" }); return; }
    setStreaming(true);
    const ctrl = new AbortController(); abortRef.current = ctrl;
    try {
      await previewAgenticStream(scenario, authToken, evt => {
        if (evt?.phase) setPhase(evt.phase);
        if (evt?.phase === "preview" && evt.preview) setPreview(evt.preview);
      }, ctrl.signal);
    } catch {
      try { const text = await previewAgentic(scenario); setPreview(text); } catch (e: any) { toast({ status: "error", title: "Preview failed", description: String(e?.message || e) }); }
    } finally { setStreaming(false); }
  };

  const handleGeneratePayload = async () => {
    if (!preview.trim()) { toast({ status: "warning", title: "Preview first" }); return; }
    setStreaming(true); setPayloadSummary(null);
    const ctrl = new AbortController(); abortRef.current = ctrl;
    try {
      await payloadAgenticStream(scenario, preview, authToken, evt => {
        if (evt?.phase) setPhase(evt.phase);
        if (evt?.phase === "payload" && evt.summary) setPayloadSummary(evt.summary);
      }, ctrl.signal);
    } catch { /* fall back to non-stream below */ }
    try {
      const res = await generatePayload(scenario, preview);
      const files = [...(res.locators || []), ...(res.pages || []), ...(res.tests || [])] as { path: string; content: string }[];
      setPayloadFiles(files);
      setPayloadSummary({ locators: res.locators?.length || 0, pages: res.pages?.length || 0, tests: res.tests?.length || 0 });
    } catch (err: any) {
      toast({ status: "error", title: "Payload failed", description: String(err?.message || err) });
    } finally { setStreaming(false); }
  };

  const doPersist = async () => {
    try {
      let writtenCount = 0;
      if (payloadFiles?.length) {
        const written = await persistFiles(payloadFiles, authToken, frameworkRepoPath || undefined);
        writtenCount = written.length;
      }
      const hasId = !!testCaseId.trim();
      if (hasId) {
        try {
          const upd = await updateTestManager({
            scenario: testCaseId.trim(),
            datasheet: datasheetName || undefined as any,
            referenceId: referenceId || undefined as any,
            idName: idName || undefined as any,
            frameworkRoot: frameworkRepoPath || undefined,
            newDescription: testCaseDescription || undefined,
            allowFreeformCreate: true,
            execute: executeValue,
          }, authToken || "");
          const partial = (!datasheetName || !referenceId || !idName) ? " (partial: created/updated without full data mapping)" : "";
          toast({ status: "success", title: "Excel updated", description: `${upd.mode}: ${upd.description}${partial}` });
          // Refresh dropdown so newly created ID appears immediately
          try {
            const rows = await listTestManager(frameworkRepoPath?.trim() || undefined);
            setTestManagerRows(rows);
          } catch {}
        } catch (excelErr: any) {
          toast({ status: "warning", title: "Excel update skipped", description: String(excelErr?.message || excelErr) });
        }
      } else {
        toast({ status: "info", title: "Provide TestCaseID", description: "Enter a TestCaseID (you can type a new one) and Persist to create a row in testmanager.xlsx." });
      }
      const fileMsg = writtenCount > 0 ? `${writtenCount} files` : 'no files (Excel only)';
      toast({ status: "success", title: "Persisted", description: fileMsg });
    } catch (err: any) { toast({ status: "error", title: "Persist failed", description: String(err?.message || err) }); }
  };

  const doPush = async () => {
    try {
      const ok = await pushChanges(frameworkBranch, frameworkCommitMessage, authToken, frameworkRepoPath || undefined);
      toast({ status: ok ? "success" : "error", title: ok ? "Push complete" : "Push failed" });
    } catch (err: any) { toast({ status: "error", title: "Push failed", description: String(err?.message || err) }); }
  };

  const ensurePayload = async () => {
    if (payloadFiles?.length) return;
    let p = preview;
    if (!p.trim()) { p = await previewAgentic(scenario); setPreview(p); }
    const res = await generatePayload(scenario, p);
    const files = [...(res.locators || []), ...(res.pages || []), ...(res.tests || [])];
    setPayloadFiles(files);
    setPayloadSummary({ locators: res.locators?.length || 0, pages: res.pages?.length || 0, tests: res.tests?.length || 0 });
  };

  // Removed unused validateMapping to avoid TS warning

  const runGeneratedTrial = async () => {
    // Trial run should NOT mutate testmanager.xlsx; skip mapping validation here.
    await ensurePayload();
    const generatedTests = (payloadFiles || [])
      .filter(f => f.path.startsWith("tests/") || f.path.endsWith(".spec.ts") || f.path.endsWith(".test.ts"));
    let testContent = generatedTests.map(f => f.content).join("\n\n");
    const selectedExistingTest = existingAssets.find(a => a.path === selectedAssetPath && a.isTest);
    // Fallback: if no generated test content, attempt running selected existing test file
    const useExisting = !testContent.trim() && selectedExistingTest;
    if (!testContent.trim() && !useExisting) {
      toast({ status: "warning", title: "No test found", description: "Generate payload to create a test OR select an existing test asset." });
      return;
    }
    setStreaming(true); setTrialLogs(""); setTrialSuccess(null);
    try {
      if (useExisting && selectedExistingTest) {
        // Run existing test file via backend helper
        const res = await trialRunExisting(selectedExistingTest.path, headedMode, frameworkRepoPath || undefined, {
          scenario: testCaseId || selectedExistingTest.path,
          datasheet: datasheetName,
          referenceId,
          idName,
          update: false,
        });
        setTrialSuccess(res.success);
        setTrialLogs(res.logs + (res.updateInfo ? "\n[testmanager] " + JSON.stringify(res.updateInfo) : ""));
        toast({ status: res.success ? "success" : "error", title: res.success ? "Trial passed" : "Trial failed" });
      } else {
        await trialRunAgenticStream(testContent, headedMode, frameworkRepoPath || undefined, authToken || undefined, evt => {
          if (evt?.phase === "update") {
            // Ignore Excel update events; Excel only updated on Persist
          } else if (evt?.phase === "chunk" && evt.data) {
            setTrialLogs(prev => prev ? prev + "\n" + evt.data : evt.data);
          } else if (evt?.phase === "done") {
            setTrialSuccess(!!evt.success);
            toast({ status: evt.success ? "success" : "error", title: evt.success ? "Trial passed" : "Trial failed" });
          } else if (evt?.phase === "error") {
            setTrialSuccess(false);
            setTrialLogs(prev => prev ? prev + "\n[error] " + evt.error : "[error] " + evt.error);
            toast({ status: "error", title: "Trial failed", description: String(evt.error || "Unknown") });
          }
        }, undefined, { scenario: testCaseId || "Generated Trial", datasheet: datasheetName, referenceId, idName, update: false });
      }
    } catch (err: any) {
      setTrialSuccess(false); setTrialLogs(String(err?.message || err)); toast({ status: "error", title: "Trial failed", description: String(err?.message || err) });
    } finally { setStreaming(false); }
  };

  // Removed runExistingTrial; users must Persist mapped Excel info then run generated trial.

  return (
    <Stack spacing={6}>
      <Heading size="lg">Test Script Generator</Heading>
      <Box bg="white" borderRadius="lg" boxShadow="sm" p={6}>
        <Stack spacing={6}>
          <Stack direction={{ base: "column", md: "row" }}>
            <FormControl maxW={{ md: "50%" }}>
              <FormLabel>Framework Repo Path</FormLabel>
              <Input value={frameworkRepoPath} onChange={e => setFrameworkRepoPath(e.target.value)} placeholder="https://github.com/org/repo.git or C:\\path\\to\\repo" />
            </FormControl>
            <FormControl maxW={{ md: "25%" }}><FormLabel>Branch</FormLabel><Input value={frameworkBranch} onChange={e => setFrameworkBranch(e.target.value)} /></FormControl>
            <FormControl maxW={{ md: "25%" }}><FormLabel>Commit Message</FormLabel><Input value={frameworkCommitMessage} onChange={e => setFrameworkCommitMessage(e.target.value)} /></FormControl>
          </Stack>
          <FormControl isDisabled={!canSearch}><FormLabel>Scenario / Keyword</FormLabel><Input value={scenario} onChange={e => onScenarioChange(e.target.value)} placeholder={canSearch ? "Create Supplier" : "Enter repo path first"} /></FormControl>
          {!canSearch && <Text color="orange.600">Repo path is required before searching.</Text>}
          {/* Existing Assets & Refined Recorder Flow BEFORE actions */}
          <Box borderWidth="1px" borderRadius="md" p={4} bg="gray.50">
            <HStack justify="space-between" mb={2}>
              <Heading size="sm">Existing Assets</Heading>
              <HStack>{inspectLoading && <Badge colorScheme="blue">Scanning…</Badge>}{inspectStatus && !inspectLoading && <Badge colorScheme={inspectStatus === 'found-existing' ? 'green' : inspectStatus === 'found-refined-only' ? 'purple' : inspectStatus === 'none' ? 'red' : 'gray'}>{inspectStatus}</Badge>}</HStack>
            </HStack>
            {inspectMessages.length > 0 && <Text fontSize="xs" color="gray.600" mb={2}>{inspectMessages.join("; ")}</Text>}
            {existingAssets.length > 0 ? (
              <Stack spacing={3}>
                {existingAssets.map((a, i) => (
                  <Box key={i} p={3} bg={selectedAssetPath === a.path ? "blue.50" : "white"} borderWidth="1px" borderRadius="md" onClick={() => setSelectedAssetPath(a.path)} cursor="pointer">
                    <HStack justify="space-between">
                      <Text fontWeight="semibold"><Code>{a.path}</Code></Text>
                      <HStack>{a.isTest && <Badge colorScheme="green">test</Badge>}{typeof a.relevance === "number" && <Badge>score {a.relevance}</Badge>}</HStack>
                    </HStack>
                    <Textarea value={a.snippet} readOnly fontSize="xs" mt={2} rows={4} />
                  </Box>
                ))}
                <HStack>
                  <Button variant="outline" onClick={() => runKeywordInspect(scenario)} isDisabled={!canSearch || streaming}>Rescan</Button>
                </HStack>
                <Text fontSize="sm" color="gray.600">
                  To execute an existing script, fill TestCaseID, TestCaseDescription, DatasheetName, ReferenceID, IDName, set Execute to Yes, click Persist, then use "Trial Run Generated".
                </Text>
              </Stack>
            ) : <Text color="gray.600">No existing assets detected.</Text>}
          </Box>
          <Box borderWidth="1px" borderRadius="md" p={4}>
            <Heading size="sm" mb={2}>Refined Recorder Flow</Heading>
            {refinedSteps.length > 0 ? (
              <Table size="sm" variant="simple">
                <Thead><Tr><Th>Step</Th><Th>Action</Th><Th>Navigation</Th><Th>Data</Th><Th>Expected</Th></Tr></Thead>
                <Tbody>{refinedSteps.map((s, i) => (<Tr key={i}><Td>{s.step}</Td><Td>{s.action}</Td><Td>{s.navigation}</Td><Td>{s.data}</Td><Td>{s.expected}</Td></Tr>))}</Tbody>
              </Table>
            ) : <Text color="gray.600">No refined flow found.</Text>}
            <HStack mt={3}><Button colorScheme="teal" onClick={handlePreview} isDisabled={streaming}>Preview From Refined Flow</Button></HStack>
          </Box>
          <HStack>
            <Button onClick={handlePreview} colorScheme="blue" isDisabled={streaming}>Preview</Button>
            <Button onClick={handleGeneratePayload} colorScheme="teal" isDisabled={streaming}>Generate Payload</Button>
          </HStack>
          <FormControl><FormLabel>Preview (editable)</FormLabel><Textarea value={preview} onChange={e => setPreview(e.target.value)} rows={8} /></FormControl>
          {/* Test Case ID + Description Selection */}
          <Stack direction={{ base: "column", md: "row" }} spacing={4}>
            <FormControl maxW={{ md: "33%" }}>
              <FormLabel>TestCaseID {loadingTestManager && <Badge ml={2} colorScheme="purple">Loading...</Badge>}</FormLabel>
              <Input list="tcid-options" value={testCaseId} onChange={e => setTestCaseId(e.target.value)} placeholder="Select existing or type new" />
              <datalist id="tcid-options">
                {testManagerRows.map(r => <option key={r.TestCaseID} value={r.TestCaseID} />)}
              </datalist>
              <Text fontSize="xs" color="gray.500" mt={1}>Choosing an existing ID pre-fills description; typing a new one will create a new row.</Text>
            </FormControl>
            <FormControl maxW={{ md: "67%" }}>
              <FormLabel>TestCaseDescription</FormLabel>
              <Textarea rows={3} value={testCaseDescription} onChange={e => setTestCaseDescription(e.target.value)} placeholder="Describe the test case" />
            </FormControl>
          </Stack>
          <Stack direction={{ base: "column", md: "row" }} spacing={4}>
            <FormControl maxW={{ md: "33%" }}><FormLabel>DatasheetName</FormLabel><Input value={datasheetName} onChange={e => setDatasheetName(e.target.value)} placeholder="supplierdata.xlsx" /></FormControl>
            <FormControl maxW={{ md: "33%" }}><FormLabel>ReferenceID</FormLabel><Input value={referenceId} onChange={e => setReferenceId(e.target.value)} placeholder="10001,10002" /></FormControl>
            <FormControl maxW={{ md: "33%" }}><FormLabel>IDName</FormLabel><Input value={idName} onChange={e => setIdName(e.target.value)} placeholder="Supplier Number" /></FormControl>
            <FormControl maxW={{ md: "33%" }}>
              <FormLabel>Execute</FormLabel>
              <Select value={executeValue} onChange={e => setExecuteValue(e.target.value)}>
                <option value="Yes">Yes</option>
                <option value="No">No</option>
              </Select>
            </FormControl>
          </Stack>
          <Box borderWidth="1px" borderRadius="md" p={4} bg="gray.50">
            <Heading size="sm" mb={2}>Test Data Sheet</Heading>
            <Stack direction={{ base:'column', md:'row' }} spacing={4} align="flex-end">
              <FormControl maxW={{ md:'40%' }}>
                <FormLabel>Select Existing Sheet</FormLabel>
                <Input list="sheet-options" value={datasheetName} onChange={e=> setDatasheetName(e.target.value)} placeholder="Choose or type filename" />
                <datalist id="sheet-options">
                  {availableSheets.map(s => <option key={s} value={s} />)}
                </datalist>
              </FormControl>
              <FormControl maxW={{ md:'40%' }}>
                <FormLabel>Upload New Sheet (.xlsx)</FormLabel>
                <Input type="file" accept=".xlsx,.xls" onChange={e => handleDatasheetUpload(e.target.files?.[0] || null)} disabled={uploading} />
              </FormControl>
              <Box minW={{ md:'20%' }}>
                <Text fontSize="xs" color="gray.600">Current: <Code>{datasheetName || 'none'}</Code></Text>
                {uploading && <Badge colorScheme="blue" mt={1}>Uploading...</Badge>}
                {loadingSheets && <Badge colorScheme="purple" mt={1}>Scanning...</Badge>}
              </Box>
            </Stack>
            <Text fontSize="xs" color="gray.500" mt={2}>Choose an existing data sheet or upload a new one. The selected filename will populate <Code>DatasheetName</Code> in <Code>testmanager.xlsx</Code> before trial execution.</Text>
          </Box>
          <HStack>
            <Button onClick={doPersist} colorScheme="green">Persist (writes files + Excel)</Button>
            <Button onClick={runGeneratedTrial} colorScheme="orange" isDisabled={streaming}>Trial Run Generated</Button>
            <Button onClick={doPush} colorScheme="purple">Push</Button>
            <Button variant="outline" onClick={() => setHeadedMode(h => !h)}>{headedMode ? "Headed: On" : "Headed: Off"}</Button>
          </HStack>
          {payloadSummary && <Text color="gray.700">Files: locators {payloadSummary.locators}, pages {payloadSummary.pages}, tests {payloadSummary.tests}</Text>}
          {trialSuccess !== null && (
            <Box bg={trialSuccess ? "green.50" : "red.50"} borderRadius="md" p={3}>
              <Text fontWeight="semibold" color={trialSuccess ? "green.700" : "red.700"}>{trialSuccess ? "Trial Passed" : "Trial Failed"}</Text>
              <Textarea value={trialLogs} readOnly rows={10} fontSize="xs" mt={2} />
            </Box>
          )}
          <SimpleGrid columns={{ base: 1, md: 2 }} gap={4}>
            <Box>
              <Text fontWeight="semibold" mb={1}>Phase</Text>
              <HStack>
                <Badge colorScheme={phase === "start" ? "blue" : "gray"}>start</Badge>
                <Badge colorScheme={phase === "gather_context" ? "blue" : "gray"}>gather_context</Badge>
                <Badge colorScheme={phase === "context_ready" ? "blue" : "gray"}>context_ready</Badge>
                <Badge colorScheme={(phase === "preview" || phase === "payload") ? "green" : "gray"}>preview/payload</Badge>
                <Badge colorScheme={phase === "done" ? "green" : phase === "error" ? "red" : "gray"}>{phase === "error" ? "error" : "done"}</Badge>
              </HStack>
            </Box>
            <Box>
              <Text fontWeight="semibold" mb={1}>Progress</Text>
              <Progress value={phase === "done" ? 100 : (phase === "preview" || phase === "payload") ? 75 : phase === "context_ready" ? 50 : phase ? 25 : 0} size="sm" colorScheme={phase === "error" ? "red" : "green"} />
            </Box>
          </SimpleGrid>
          {(payloadFiles?.length ?? 0) > 0 && (
            <Box borderWidth="1px" borderRadius="md" p={4}>
              <Heading size="sm" mb={3}>Generated Files ({payloadFiles?.length ?? 0})</Heading>
              <Stack spacing={4}>{(payloadFiles ?? []).map((f, i) => (
                <Box key={`${f.path}-${i}`} borderWidth="1px" borderRadius="md" p={3} bg="gray.50">
                  <Text fontWeight="semibold" mb={2}><Code>{f.path}</Code></Text>
                  <Textarea value={f.content} readOnly fontFamily="mono" rows={8} />
                </Box>
              ))}</Stack>
            </Box>
          )}
        </Stack>
      </Box>
    </Stack>
  );
}
