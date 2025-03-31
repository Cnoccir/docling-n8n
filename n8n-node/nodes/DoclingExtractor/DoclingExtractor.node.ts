import { IExecuteFunctions } from 'n8n-core';
import {
	INodeExecutionData,
	INodeType,
	INodeTypeDescription,
	NodeOperationError,
} from 'n8n-workflow';
import FormData from 'form-data';

export class DoclingExtractor implements INodeType {
	description: INodeTypeDescription = {
		displayName: 'Docling Extractor',
		name: 'doclingExtractor',
		group: ['transform'],
		version: 1,
		description: 'Process documents with enhanced extraction for RAG workflows',
		defaults: {
			name: 'Docling Extractor',
			color: '#125580',
		},
		inputs: ['main'],
		outputs: ['main'],
		properties: [
			{
				displayName: 'Operation',
				name: 'operation',
				type: 'options',
				options: [
					{
						name: 'Standard Extraction',
						value: 'extract',
						description: 'Extract content from document',
					},
					{
						name: 'Supabase Ready',
						value: 'extractSupabase',
						description: 'Extract and format for Supabase integration',
					},
				],
				default: 'extractSupabase',
				required: true,
			},
			{
				displayName: 'Docling API URL',
				name: 'apiUrl',
				type: 'string',
				default: 'http://localhost:8000',
				required: true,
				description: 'Base URL of the Docling extractor API (without /api path)',
			},
			{
				displayName: 'Document',
				name: 'binaryPropertyName',
				type: 'string',
				default: 'data',
				required: true,
				displayOptions: {
					show: {
						operation: ['extract', 'extractSupabase'],
					},
				},
				description: 'Name of the binary property that contains the document file',
			},
			{
				displayName: 'File ID',
				name: 'fileId',
				type: 'string',
				default: '',
				required: false,
				displayOptions: {
					show: {
						operation: ['extract', 'extractSupabase'],
					},
				},
				description: 'Optional identifier for the document (will be generated if not provided)',
			},
			{
				displayName: 'File Title',
				name: 'fileTitle',
				type: 'string',
				default: '',
				required: false,
				displayOptions: {
					show: {
						operation: ['extract', 'extractSupabase'],
					},
				},
				description: 'Optional title for the document (will use filename if not provided)',
			},
			{
				displayName: 'Advanced Options',
				name: 'options',
				type: 'collection',
				placeholder: 'Add Option',
				default: {},
				displayOptions: {
					show: {
						operation: ['extract', 'extractSupabase'],
					},
				},
				options: [
					{
						displayName: 'Extract Technical Terms',
						name: 'extractTechnicalTerms',
						type: 'boolean',
						default: true,
						description: 'Whether to extract technical terms from the document',
					},
					{
						displayName: 'Extract Procedures',
						name: 'extractProcedures',
						type: 'boolean',
						default: true,
						description: 'Whether to extract procedures and parameters from the document',
					},
					{
						displayName: 'Extract Relationships',
						name: 'extractRelationships',
						type: 'boolean',
						default: true,
						description: 'Whether to extract relationships between concepts',
					},
					{
						displayName: 'Process Images',
						name: 'processImages',
						type: 'boolean',
						default: true,
						description: 'Whether to process and extract images from the document',
					},
					{
						displayName: 'Process Tables',
						name: 'processTables',
						type: 'boolean',
						default: true,
						description: 'Whether to process and extract tables from the document',
					},
					{
						displayName: 'Chunk Size',
						name: 'chunkSize',
						type: 'number',
						default: 500,
						description: 'Size of text chunks for extraction',
					},
					{
						displayName: 'Chunk Overlap',
						name: 'chunkOverlap',
						type: 'number',
						default: 100,
						description: 'Overlap between chunks',
					},
				],
			},
		],
	};

	async execute(this: IExecuteFunctions): Promise<INodeExecutionData[][]> {
		const items = this.getInputData();
		const returnItems: INodeExecutionData[] = [];

		// Process each input item
		for (let itemIndex = 0; itemIndex < items.length; itemIndex++) {
			try {
				// Retrieve node parameters
				const operation = this.getNodeParameter('operation', itemIndex) as string;
				const apiUrl = this.getNodeParameter('apiUrl', itemIndex) as string;
				const binaryPropertyName = this.getNodeParameter('binaryPropertyName', itemIndex) as string;
				const fileId = this.getNodeParameter('fileId', itemIndex, '') as string;
				const fileTitle = this.getNodeParameter('fileTitle', itemIndex, '') as string;
				const options = this.getNodeParameter('options', itemIndex, {}) as {
					extractTechnicalTerms?: boolean;
					extractProcedures?: boolean;
					extractRelationships?: boolean;
					processImages?: boolean;
					processTables?: boolean;
					chunkSize?: number;
					chunkOverlap?: number;
				};

				// Verify binary data exists on the item
				if (items[itemIndex].binary === undefined) {
					throw new NodeOperationError(
						this.getNode(),
						'No binary data exists on item!',
						{ itemIndex },
					);
				}

				const binaryData = items[itemIndex].binary![binaryPropertyName];
				if (binaryData === undefined) {
					throw new NodeOperationError(
						this.getNode(),
						`No binary data property '${binaryPropertyName}' exists on item!`,
						{ itemIndex },
					);
				}

				// Create FormData for the file upload
				const formData = new FormData();
				const buffer = Buffer.from(binaryData.data, 'base64');
				formData.append('file', buffer, {
					filename: binaryData.fileName || 'document.pdf',
					contentType: binaryData.mimeType,
				});

				// Append additional parameters if provided
				if (fileId) {
					formData.append('file_id', fileId);
				}
				if (fileTitle) {
					formData.append('file_title', fileTitle);
				}
				if (options.extractTechnicalTerms !== undefined) {
					formData.append('extract_technical_terms', options.extractTechnicalTerms.toString());
				}
				if (options.extractProcedures !== undefined) {
					formData.append('extract_procedures', options.extractProcedures.toString());
				}
				if (options.extractRelationships !== undefined) {
					formData.append('extract_relationships', options.extractRelationships.toString());
				}
				if (options.processImages !== undefined) {
					formData.append('process_images', options.processImages.toString());
				}
				if (options.processTables !== undefined) {
					formData.append('process_tables', options.processTables.toString());
				}
				if (options.chunkSize !== undefined) {
					formData.append('chunk_size', options.chunkSize.toString());
				}
				if (options.chunkOverlap !== undefined) {
					formData.append('chunk_overlap', options.chunkOverlap.toString());
				}

				// Determine the endpoint URL based on the chosen operation
				let endpoint = '';
				if (operation === 'extract') {
					endpoint = '/api/extract';
				} else if (operation === 'extractSupabase') {
					endpoint = '/api/extract-supabase-ready';
				}

				// Adjust endpoint string to concatenate correctly with apiUrl
				if (apiUrl.endsWith('/') && endpoint.startsWith('/')) {
					endpoint = endpoint.substring(1);
				} else if (!apiUrl.endsWith('/') && !endpoint.startsWith('/')) {
					endpoint = '/' + endpoint;
				}

				// Make the HTTP request to the Docling API
				const response = await this.helpers.httpRequest({
					method: 'POST',
					url: apiUrl + endpoint,
					body: formData,
					headers: {
						...formData.getHeaders(),
					},
					returnFullResponse: true,
				});

				// Process and enhance the response for Supabase-ready extraction
				let processedResponse: any = {};
				if (operation === 'extractSupabase') {
					processedResponse = {
						pdf_id: response.file_id,
						file_title: response.file_title,
						content_types: {
							text_chunks_count: (response.text_chunks || []).length,
							images_count: (response.images || []).length,
							tables_count: (response.tables || []).length,
							procedures_count: (response.procedures || []).length,
						},
						document_metadata: response.document_metadata,
						full_extraction: response,
					};
				} else {
					processedResponse = response;
				}

				returnItems.push({
					json: processedResponse,
					binary: {},
				});
			} catch (error) {
				if (this.continueOnFail()) {
					returnItems.push({
						json: { error: error.message },
						binary: {},
					});
					continue;
				}
				throw error;
			}
		}

		return [returnItems];
	}
}
