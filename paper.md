---
title: 'Droplet Wall Interaction Tool: A Python based analysis tool for droplet movement during free movement and wall contact'
tags:
  - Python
  - laboratory automation
  - image analysis
  - droplet experiments
  - scientific software
  - contact angle measurement
authors:
  - name: Kristina Mielke
    orcid: 0009-0009-9946-3315
    corresponding: true
    affiliation: 1
  - name: Arif Rasim Can
    corresponding: false
    affiliation: 1
  - name: Andreas Jupke
    orcid: 0000-0001-6551-5695
    corresponding: true
    affiliation: 1,2

affiliations:
 - name: Fluid Process Engineering (AVT.FVT), RWTH Aachen University, 52074 Aachen, Germany
   index: 1
   ror: https://ror.org/04xfq0f34
 - name: Institute for Bio- and Geosciences (IBG-2), Forschungszentrum Jülich GmbH, 52428 Jülich, Germany
   index: 2

date: 31 March 2026
bibliography: paper.bib
---

# Summary
Droplet hydrodynamics play a central role in many chemical engineering and industrial separation processes, including liquid–liquid extraction, multiphase reactors, and microfluidic applications. In such systems, the motion, deformation, and interaction of droplets with surrounding geometries strongly influence residence times, mass transfer, and overall apparatus performance. Experimental investigations of these effects require large numbers of high-speed video recordings under varying conditions. As a result, researchers are often confronted with extensive datasets consisting of hundreds of videos that must be evaluated consistently. Manual analysis is time-consuming and limits reproducibility. The Droplet Wall Interaction Tool was developed to address this challenge by providing an automated and extensible platform for droplet motion analysis across different experimental scenarios. 

# Statement of need & state of the field
Understanding how wall contact and apparatus internals influence droplet motion requires systematic comparison against a well-defined baseline case. In particular, the freely rising droplet without geometric constraints represents an essential reference scenario. Only by quantifying this baseline behavior can researchers determine how droplets are altered by walls, channels, or structured packings. To quantify this behavior, the droplet center can be tracked by analytical tools to meausure the droplet velocity and trajectory. Measuring width and height of the drop enables understanding of droplet deformation. Additionally, droplet contact angles and contact lines should be evaluated for influence of wetting in an apparatus. A wide range of algorithms and open-source packages exist for droplet contour detection, image segmentation, and contact angle measurement [@Sibirtsev.2023; @Huang.2021b; @Allan.2025]. In particular, tools for sessile droplet analysis on horizontal substrates are commonly used in surface science and wetting research. These approaches are well suited for static and symmetric droplets under controlled laboratory conditions. However, existing tools often become insufficient when droplets are moving, deforming, or interacting with inclined or structured surfaces. Furthermore, most software solutions focus on isolated tasks such as static contact angle determination and do not provide integrated analysis of droplet velocity, deformation metrics, and contact line dynamics within a single framework. [@Huang.2021b] Another key limitation is scalability. While some tools allow automated processing of individual videos, they typically lack support for dataset-level batch evaluation, which is essential in experimental campaigns producing hundreds of recordings.

# Software design
A central design requirement was to combine analytical algorithms with an interactive graphical user interface (GUI) that allows researchers to process large datasets efficiently while maintaining transparency of the underlying analysis. The software is implemented in Python. Droplet detection and contour extraction are based on established methods from the OpenCV library. In particular, edge-based segmentation using the Canny algorithm provides a reliable foundation for robust droplet recognition across experimental scenarios, including freely rising droplets and droplets interacting with inclined or structured surfaces. Users can define regions of interest, adjust baseline parameters, and immediately verify how selected settings influence droplet detection. Importantly, the interface provides real-time visual overlays of detected contours and intermediate processing steps. This allows researchers to confirm that droplets are correctly recognized throughout the analysis and reduces the risk of unnoticed parameter misconfiguration. The image analysis workflow begins with preprocessing steps such as cropping, rotation, and background correction to ensure consistent droplet visibility. Droplet contours are then extracted and geometric features such as area and equivalent diameter are computed. Depending on the experimental mode, baseline intersections are evaluated to determine contact line and advancing or receding contact angles. Contact angles are measured using the tangent method due to its robustness of analyzing asymmetric droplet shapes. Droplet center positions are tracked over time, enabling velocity calculations from trajectory data. Results are exported in standardized Excel formats.

# Research impact statement
The Droplet Wall Interaction Tool has already been successfully applied in research on liquid–liquid extraction and droplet–wall interaction phenomena. Mielke et al. used the software to quantify the influence of stainless-steel wall contact on the velocity of butyl acetate droplets. Their results showed that droplet deformation oscillations occur during free rise and that these oscillations are significantly reduced when droplets interact with a wall surface. [@Mielke.2025] Potter et al. applied the tool to investigate the invasiveness of film thickness sensors in structured packings. By comparing droplet velocities of different organic phases, including butanol, silicone oil, and butyl acetate, on both stainless-steel and polymer sensor surfaces, they demonstrated that the sensor material does not significantly alter droplet hydrodynamics. This supports the applicability of such sensors for usage in structured packings without disturbing flow behavior.[@Potter.2026] These applications demonstrate that the software already contributes to reproducible experimental workflows and provides a foundation for ongoing studies in droplet dynamics.

# AI usage disclosure
Generative AI tools were used during the development of this project. AI assistance was applied to improve code documentation by adding explanatory comments and to support language refinement of the manuscript, as English is not the native language of the authors.

The authors confirm that all AI-assisted outputs were carefully reviewed, edited, and validated by the human authors. All scientific interpretations, software design decisions, and final text content remain the responsibility of the authors.



