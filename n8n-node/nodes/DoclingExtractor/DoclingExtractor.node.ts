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
		description: 'Process PDF documents using Docling to extract text, tables, images, and more',
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
						description: 'Extract content from PDF document',
					},
					{
						name: 'Qdrant Ready',
						value: 'extractQdrant',
						description: 'Extract and format for Qdrant vector database',
					},
					{
						name: 'MongoDB Ready',
						value: 'extractMongoDB',
						description: 'Extract and format for MongoDB document database',
					},
					{
						name: 'Get Processing Status',
						value: 'status',
						description: 'Check status of a processing job',
					},
					{
						name: 'Get Results',
						value: 'results',
						description: 'Get results of a completed processing job',
					},
				],
				default: 'extract',
				required: true,
			},
			{
				displayName: 'Docling API URL',
				name: 'apiUrl',
				type: 'string',
				default: 'http://localhost:8000',
				required: true,
				description: 'Base URL of the Docling extraction API',
			},
			{
				displayName: 'API Key',
				name: 'apiKey',
				type: 'string',
				default: '',
				required: false,
				description: 'API key for authentication (if required)',
			},
			// For status and results operations
			{
				displayName: 'PDF ID',
				name: 'pdfId',
				type: 'string',
				default: '',
				required: true,
				displayOptions: {
					show: {
						operation: ['status', 'results'],
					},
				},
				description: 'ID of the PDF document to check',
			},
			// For operations that require a file
			{
				displayName: 'PDF Document',
				name: 'binaryPropertyName',
				type: 'string',
				default: 'data',
				required: true,
				displayOptions: {
					show: {
						operation: ['extract', 'extractQdrant', 'extractMongoDB'],
					},
				},
				description: 'Name of the binary property that contains the PDF file',
			},
			{
				displayName: 'PDF ID',
				name: 'pdfId',
				type: 'string',
				default: '',
				required: false,
				displayOptions: {
					show: {
						operation: ['extract', 'extractQdrant', 'extractMongoDB'],
					},
				},
				description: 'Optional identifier for the PDF document (will be generated if not provided)',
			},
			{
				displayName: 'Advanced Options',
				name: 'options',
				type: 'collection',
				placeholder: 'Add Option',
				default: {},
				displayOptions: {
					show: {
						operation: ['extract', 'extractQdrant', 'extractMongoDB'],
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
						description: 'Whether to extract concept relationships from the document',
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
			{
				displayName: 'Output Format',
				name: 'outputFormat',
				type: 'options',
				options: [
					{
						name: 'Combined Object',
						value: 'combined',
						description: 'Return all data in a single JSON object',
					},
					{
						name: 'Separate Items',
						value: 'separate',
						description: 'Return separate items for markdown, tables, images, etc.',
					},
				],
				default: 'combined',
				description: 'Specify how the extracted data should be returned',
				displayOptions: {
					show: {
						operation: ['extract', 'extractQdrant', 'extractMongoDB', 'results'],
					},
				},
			},
		],
	};

	async execute(this: IExecuteFunctions): Promise<INodeExecutionData[][]> {
		const items = this.getInputData();
		const returnItems: INodeExecutionData[] = [];

		// For each item
		for (let itemIndex = 0; itemIndex < items.length; itemIndex++) {
			try {
				// Get common parameters
				const operation = this.getNodeParameter('operation', itemIndex) as string;
				const apiBaseUrl = this.getNodeParameter('apiUrl', itemIndex) as string;
				const apiKey = this.getNodeParameter('apiKey', itemIndex, '') as string;
				const outputFormat = this.getNodeParameter('outputFormat', itemIndex, 'combined') as string;

				let responseData;

				// Handle different operations
				if (operation === 'status') {
					// Get processing status
					const pdfId = this.getNodeParameter('pdfId', itemIndex) as string;
					const statusUrl = `${apiBaseUrl}/api/status/${pdfId}`;

					responseData = await this.helpers.request({
						method: 'GET',
						url: statusUrl,
						headers: apiKey ? { 'x-api-key': apiKey } : undefined,
					});

					returnItems.push({
						json: typeof responseData === 'string' ? JSON.parse(responseData) : responseData,
						binary: {},
					});

				} else if (operation === 'results') {
					// Get processing results
					const pdfId = this.getNodeParameter('pdfId', itemIndex) as string;
					const resultsUrl = `${apiBaseUrl}/api/results/${pdfId}`;

					responseData = await this.helpers.request({
						method: 'GET',
						url: resultsUrl,
						headers: apiKey ? { 'x-api-key': apiKey } : undefined,
					});

					// Process the response based on the output format
					if (outputFormat === 'combined') {
						returnItems.push({
							json: typeof responseData === 'string' ? JSON.parse(responseData) : responseData,
							binary: {},
						});
					} else {
						// Create separate items for different types of content
						this.createSeparateItems(responseData, returnItems);
					}

				} else {
					// Operations that require file upload: extract, extractQdrant, extractMongoDB
					const binaryPropertyName = this.getNodeParameter('binaryPropertyName', itemIndex) as string;
					const pdfId = this.getNodeParameter('pdfId', itemIndex, '') as string;
					const options = this.getNodeParameter('options', itemIndex, {}) as {
						extractTechnicalTerms?: boolean;
						extractProcedures?: boolean;
						extractRelationships?: boolean;
						processImages?: boolean;
						processTables?: boolean;
						chunkSize?: number;
						chunkOverlap?: number;
					};

					// Get binary data
					if (items[itemIndex].binary === undefined) {
						throw new NodeOperationError(
							this.getNode(),
							'No binary data exists on item!',
							{ itemIndex },
						);
					}

					const binaryData = items[itemIndex].binary[binaryPropertyName];
					if (binaryData === undefined) {
						throw new NodeOperationError(
							this.getNode(),
							`No binary data property "${binaryPropertyName}" does not exists on item!`,
							{ itemIndex },
						);
					}

					// Create FormData for file upload
					const formData = new FormData();

					// Add PDF ID if provided
					if (pdfId) {
						formData.append('pdf_id', pdfId);
					}

					// Add API key if provided
					if (apiKey) {
						formData.append('api_key', apiKey);
					}

					// Add processing options
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

					// Add file
					const buffer = Buffer.from(binaryData.data, 'base64');
					formData.append('file', buffer, {
						filename: binaryData.fileName || 'document.pdf',
						contentType: binaryData.mimeType,
					});

					// Determine the endpoint URL based on operation
					let endpoint;
					switch (operation) {
						case 'extractQdrant':
							endpoint = '/api/extract-qdrant-ready';
							break;
						case 'extractMongoDB':
							endpoint = '/api/extract-mongodb-ready';
							break;
						default:
							endpoint = '/api/extract';
							break;
					}

					// Make request to API
					const requestOptions = {
						method: 'POST',
						url: `${apiBaseUrl}${endpoint}`,
						body: formData,
						headers: {
							...formData.getHeaders(),
						},
					};

					responseData = await this.helpers.request(requestOptions);
					const parsedData = typeof responseData === 'string' ? JSON.parse(responseData) : responseData;

					// Process the response based on output format
					if (outputFormat === 'combined') {
						// Create a single item with all data
						returnItems.push({
							json: parsedData,
							binary: {},
						});
					} else {
						// Create separate items for different types of content
						this.createSeparateItems(parsedData, returnItems);
					}
				}

			} catch (error) {
				if (this.continueOnFail()) {
					returnItems.push({
						json: {
							error: error.message,
						},
					});
					continue;
				}
				throw error;
			}
		}

		return [returnItems];
	}

	/**
	 * Create separate items for different types of content in the response
	 */
	private createSeparateItems(data: any, returnItems: INodeExecutionData[]): void {
		// Main Markdown item
		returnItems.push({
			json: {
				pdf_id: data.pdf_id,
				content_type: 'markdown',
				content: data.markdown,
				metadata: data.metadata,
			},
		});

		// Table items
		if (data.tables && Array.isArray(data.tables)) {
			for (const [index, table] of data.tables.entries()) {
				returnItems.push({
					json: {
						pdf_id: data.pdf_id,
						content_type: 'table',
						index,
						...table,
					},
				});
			}
		}

		// Image items
		if (data.images && Array.isArray(data.images)) {
			for (const [index, image] of data.images.entries()) {
				returnItems.push({
					json: {
						pdf_id: data.pdf_id,
						content_type: 'image',
						index,
						...image,
					},
				});
			}
		}

		// Technical terms item
		if (data.technical_terms && Array.isArray(data.technical_terms)) {
			returnItems.push({
				json: {
					pdf_id: data.pdf_id,
					content_type: 'technical_terms',
					terms: data.technical_terms,
				},
			});
		}

		// Procedures items
		if (data.procedures && Array.isArray(data.procedures)) {
			for (const [index, procedure] of data.procedures.entries()) {
				returnItems.push({
					json: {
						pdf_id: data.pdf_id,
						content_type: 'procedure',
						index,
						...procedure,
					},
				});
			}
		}

		// Parameters items
		if (data.parameters && Array.isArray(data.parameters)) {
			for (const [index, parameter] of data.parameters.entries()) {
				returnItems.push({
					json: {
						pdf_id: data.pdf_id,
						content_type: 'parameter',
						index,
						...parameter,
					},
				});
			}
		}

		// Chunks items (for vector database)
		if (data.chunks && Array.isArray(data.chunks)) {
			for (const [index, chunk] of data.chunks.entries()) {
				returnItems.push({
					json: {
						pdf_id: data.pdf_id,
						content_type: 'chunk',
						index,
						...chunk,
					},
				});
			}
		}

		// Relationships item
		if (data.concept_relationships && Array.isArray(data.concept_relationships)) {
			returnItems.push({
				json: {
					pdf_id: data.pdf_id,
					content_type: 'relationships',
					relationships: data.concept_relationships,
				},
			});
		}

		// Summary item if available
		if (data.summary) {
			returnItems.push({
				json: {
					pdf_id: data.pdf_id,
					content_type: 'summary',
					...data.summary,
				},
			});
		}

		// Special formats for different operations
		if (data.qdrant_chunks) {
			returnItems.push({
				json: {
					pdf_id: data.pdf_id,
					content_type: 'qdrant_chunks',
					chunks: data.qdrant_chunks,
				},
			});
		}

		if (data.mongodb_document) {
			returnItems.push({
				json: {
					pdf_id: data.pdf_id,
					content_type: 'mongodb_document',
					document: data.mongodb_document,
				},
			});
		}
	}
}
